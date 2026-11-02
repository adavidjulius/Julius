import { Command } from 'commander';
import * as fs from 'fs';
import * as path from 'path';
import { runDirMode } from './modes/dir.js';
import { runRepoMode } from './modes/repo.js';
import { runUrlMode } from './modes/url.js';
import { runUltraMode } from './modes/ultra.js';
import { generateDesignMd } from './writers/design-md.js';
import { generateSkill } from './writers/skill.js';
import { CLIOptions, DesignProfile } from './types.js';
import {
  // Import or destructure parameter VERSION
  VERSION,
  // Import or destructure parameter showLogo
  showLogo,
  // Import or destructure parameter showMissionBrief
  showMissionBrief,
  // Import or destructure parameter startSpinner
  startSpinner,
  // Import or destructure parameter succeedSpinner
  succeedSpinner,
  // Import or destructure parameter failSpinner
  failSpinner,
  // Import or destructure parameter warnLine
  warnLine,
  // Import or destructure parameter showUltraPlaywrightError
  showUltraPlaywrightError,
  // Import or destructure parameter showResults
  showResults,
  // Import or destructure parameter runInteractivePrompts
  runInteractivePrompts,
} from './ui.js';

const program = new Command();

program
  .name('skillui')
  .description('Reverse-engineer design systems from any project. Pure static analysis — no AI, no API keys.')
  .version(VERSION)
  .option('--dir <path>', 'Scan a local project directory')
  .option('--repo <url>', 'Clone and scan a git repository')
  .option('--url <url>', 'Crawl a live website')
  .option('--out <path>', 'Output directory', './')
  .option('--name <string>', 'Override project name')
  .option('--no-skill', 'Output DESIGN.md only, skip .skill packaging')
  .option('--format <format>', 'Output format: design-md | skill | both', 'both')
  .option('--mode <mode>', 'Extraction mode: default | ultra', 'default')
  .option('--screens <number>', 'Ultra mode: max pages to crawl (default: 5)', '5')
  .option('--login', 'Launch an interactive browser to log in before extraction')
  .action(async (opts: CLIOptions) => {
    // Always show the logo on every command
    await showLogo();

    const modes = [opts.dir, opts.repo, opts.url].filter(Boolean);

    if (modes.length === 0) {
      // No args — ask step-by-step questions
      const answers = await runInteractivePrompts();
      if (!answers) process.exit(0);
      opts.url  = answers.source === 'url'  ? answers.target : undefined;
      opts.dir  = answers.source === 'dir'  ? answers.target : undefined;
      opts.repo = answers.source === 'repo' ? answers.target : undefined;
      opts.mode = answers.mode;
      opts.out  = answers.out || './';
    } else if (modes.length > 1) {
      console.error('  Error: Specify only one of --dir, --repo, or --url\n');
      process.exit(1);
    }

    // ── Determine target label for brief ──────────────────────────────
    const target = opts.url || opts.dir || opts.repo || '';
    showMissionBrief(opts.mode || 'default', target, path.resolve(opts.out));

    try {
      let profile: DesignProfile;
      let screenshotPath: string | null = null;
      let userDataDir: string | undefined;

      const outputDir = path.resolve(opts.out);
      fs.mkdirSync(outputDir, { recursive: true });

      // ── Dir mode ──────────────────────────────────────────────────
      if (opts.dir) {
        const resolvedDir = path.resolve(opts.dir);
        if (!fs.existsSync(resolvedDir)) {
          console.error(`\n  Error: Directory not found: ${resolvedDir}\n`);
          process.exit(1);
        }
        const sp = startSpinner('Scanning local directory...');
        try {
          profile = await runDirMode(resolvedDir, opts.name);
          succeedSpinner(sp, 'Directory scan', `${profile.colors.length} colors · ${profile.components.length} components`);
        } catch (e: any) {
          failSpinner(sp, 'Directory scan', e.message);
          throw e;
        }

      // ── Repo mode ─────────────────────────────────────────────────
      } else if (opts.repo) {
        const sp = startSpinner('Cloning repository...');
        try {
          profile = await runRepoMode(opts.repo, opts.name);
          succeedSpinner(sp, 'Repo clone + scan', `${profile.colors.length} colors · ${profile.components.length} components`);
        } catch (e: any) {
          failSpinner(sp, 'Repo clone', e.message);
          throw e;
        }

      // ── URL mode ──────────────────────────────────────────────────
      } else {
        const safeName = (opts.name || new URL(opts.url!).hostname.replace(/^www\./, '').split('.')[0])
          .replace(/[^a-zA-Z0-9-_]/g, '-').toLowerCase();
        const skillDir = path.join(outputDir, `${safeName}-design`);
        fs.mkdirSync(path.join(skillDir, 'screenshots'), { recursive: true });

        if (opts.login) {
          const { loadPlaywright } = await import('./playwright-loader.js');
          const playwright = loadPlaywright();
          if (!playwright) {
            console.error('\n  Error: Playwright must be installed for interactive login (--login).\n');
            process.exit(1);
          }
          const os = await import('os');
          const readline = await import('readline');
          userDataDir = path.join(os.tmpdir(), `skillui-auth-${Date.now()}`);
          console.log('\n  [Login Mode] Launching interactive browser...');
          const context = await playwright.chromium.launchPersistentContext(userDataDir, { 
            headless: false, 
            channel: 'chrome',
            ignoreDefaultArgs: ['--enable-automation'],
            args: ['--disable-blink-features=AutomationControlled']
          });
          const page = await context.newPage();
          await page.goto(opts.url!);
          const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
          await new Promise<void>(resolve => rl.question('\n  Log in, start a chat, and set up the UI perfectly. Then press ENTER here to start scraping...', () => resolve()));
          opts.url = page.url(); // Capture the exact chat URL the user navigated to!
          rl.close();
          await context.close();
          console.log('  [Login Mode] Session saved! Starting background extraction...\n');
        }

        const sp1 = startSpinner('Fetching HTML + CSS...');
        let urlResult: Awaited<ReturnType<typeof runUrlMode>>;
        try {
          urlResult = await runUrlMode(opts.url!, opts.name, skillDir, userDataDir);
          const { cssColorCount, cssFontCount, computedColorCount, hadPlaywright } = urlResult;
          const detail = hadPlaywright
            ? `${cssColorCount} CSS colors · ${computedColorCount} computed · ${cssFontCount} fonts`
            : `${cssColorCount} colors · ${cssFontCount} fonts (Playwright not found)`;
          succeedSpinner(sp1, 'CSS + token extraction', detail);
          if (!hadPlaywright) {
            warnLine('Playwright not installed — computed style extraction skipped');
            warnLine('Fix: npm install -g playwright && npx playwright install chromium');
          }
        } catch (e: any) {
          failSpinner(sp1, 'CSS + token extraction', e.message);
          throw e;
        }
        profile = urlResult.profile;
        screenshotPath = urlResult.screenshotPath;
      }

      // ── Ultra mode (URL only) ──────────────────────────────────────
      const isUltra = opts.mode === 'ultra' && !!opts.url;
      let ultraAnimations: import('./types-ultra.js').FullAnimationResult | null = null;

      if (isUltra) {
        const ultraScreens = Math.max(1, Math.min(20, parseInt(opts.screens, 10) || 5));
        const safeName = (opts.name || new URL(opts.url!).hostname.replace(/^www\./, '').split('.')[0])
          .replace(/[^a-zA-Z0-9-_]/g, '-').toLowerCase();
        const skillDir = path.join(path.resolve(opts.out), `${safeName}-design`);

        // Check playwright before spinning up ultra
        const { loadPlaywright } = await import('./playwright-loader.js');
        if (!loadPlaywright()) {
          showUltraPlaywrightError();
          warnLine('Continuing without ultra features...');
        } else {
          const spAnim = startSpinner('Capturing scroll journey + animations...');
          try {
            const ultraResult = await runUltraMode(opts.url!, profile, skillDir, { screens: ultraScreens }, userDataDir);
            ultraAnimations = ultraResult.animations;
            const kf = ultraAnimations.keyframes.length;
            const sf = ultraAnimations.scrollFrames.length;
            const libs = ultraAnimations.libraries.map(l => l.name).join(', ') || 'none';
            succeedSpinner(spAnim, 'Ultra extraction', `${sf} scroll frames · ${kf} keyframes · ${libs}`);
          } catch (e: any) {
            failSpinner(spAnim, 'Ultra extraction', e.message);
            throw e;
          }
        }
      }

      // ── Generate + write outputs ───────────────────────────────────
      const shouldWriteDesignMd = opts.format === 'design-md' || opts.format === 'both';
      const shouldWriteSkill = opts.skill !== false && (opts.format === 'skill' || opts.format === 'both');

      const designMdContent = generateDesignMd(profile, screenshotPath);
      const safeName = profile.projectName.replace(/[^a-zA-Z0-9-_]/g, '-').toLowerCase();
      const designDir = path.join(path.resolve(opts.out), `${safeName}-design`);
      fs.mkdirSync(designDir, { recursive: true });

      let designMdPath: string | undefined;
      if (shouldWriteDesignMd) {
        const spWrite = startSpinner('Writing DESIGN.md...');
        designMdPath = path.join(designDir, 'DESIGN.md');
        fs.writeFileSync(designMdPath, designMdContent, 'utf-8');
        succeedSpinner(spWrite, 'DESIGN.md', designMdPath);
      }

      let skillFilePath: string | undefined;
      let skillInstalled = false;
      if (shouldWriteSkill) {
        const spSkill = startSpinner('Bundling .skill package...');
        try {
          const result = await generateSkill(profile, designMdContent, path.resolve(opts.out), screenshotPath, ultraAnimations);
          skillFilePath = result.skillFile;
          succeedSpinner(spSkill, '.skill package', skillFilePath);

          // ── Auto-install to ~/.julius/skills/ + write JULIUS.md ──
          // Use the actual skillDir folder name (e.g. "ascend-design") as the skill name
          const skillFolderName = path.basename(result.skillDir);
          writeJuliusMd(result.skillDir, skillFolderName, profile.projectName);
          skillInstalled = installSkillForJulius(result.skillDir, skillFolderName);
        } catch (e: any) {
          failSpinner(spSkill, '.skill package', e.message);
          throw e;
        }
      }

      // ── Show results panel ─────────────────────────────────────────
      showResults({
        // Import or destructure parameter profile
        profile,
        animations: ultraAnimations ?? undefined,
        // Import or destructure parameter skillFilePath
        skillFilePath,
        // Import or destructure parameter designMdPath
        designMdPath,
        projectName: safeName,
        // Import or destructure parameter skillInstalled
        skillInstalled,
      });

    } catch (err: any) {
      console.error(`\n  Error: ${err.message || err}\n`);
      process.exit(1);
    }
  });

program.parse();

// ── Write JULIUS.md & JULIUS_SKILL.yaml into the design folder so Julius picks it up ────
function writeJuliusMd(skillDir: string, safeName: string, projectName: string): void {
  try {
    const juliusMdPath = path.join(skillDir, 'JULIUS.md');
    if (!fs.existsSync(juliusMdPath)) {
      // Define constant content set to `# ${projectName} Design System
      const content = `# ${projectName} Design System

This project uses the **${projectName}** design system extracted by skillui for Julius.

## How to use in Julius

Read \`SKILL.md\` in this directory for the full design system reference before writing any UI code.

Key files:
- \`SKILL.md\` — master design reference (read this first)
- \`JULIUS_SKILL.yaml\` — Julius skill platform manifest
- \`references/DESIGN.md\` — extended tokens and component specs
- \`references/ANIMATIONS.md\` — motion and keyframe specs
- \`references/LAYOUT.md\` — grid and layout containers
- \`references/COMPONENTS.md\` — DOM component patterns
- \`screens/scroll/\` — scroll journey screenshots (study before implementing)

When building any UI with Julius, always read SKILL.md first and match colors, fonts, spacing, and motion exactly.
`;
      // Execute statement: fs.writeFileSync(juliusMdPath, content, 'utf-8');
      fs.writeFileSync(juliusMdPath, content, 'utf-8');
    }

    // Define constant manifestPath set to path.join(skillDir, 'JULIUS_SKILL.yaml');
    const manifestPath = path.join(skillDir, 'JULIUS_SKILL.yaml');
    // Check condition: !fs.existsSync(manifestPath)
    if (!fs.existsSync(manifestPath)) {
      const yamlContent = `name: ${safeName}
version: 1.0.0
description: Design system skill for ${projectName}
publisher: julius-skillui
license: MIT
permissions:
  required:
    - filesystem.read
  role: standard
tags:
  - design-system
  - skillui
  - ${safeName}
execution_mode: interpreter
entrypoint: SKILL.md
`;
      fs.writeFileSync(manifestPath, yamlContent, 'utf-8');
    }
  } catch { /* non-fatal */ }
}

// ── Auto-install skill to ~/.julius/skills/<name>/SKILL.md ───────────────
function installSkillForJulius(skillDir: string, safeName: string): boolean {
  try {
    const skillMdSrc = path.join(skillDir, 'SKILL.md');
    if (!fs.existsSync(skillMdSrc)) return false;

    const homeDir = process.env.USERPROFILE || process.env.HOME || '';
    if (!homeDir) return false;

    const userDestDir = path.join(homeDir, '.julius', 'skills', safeName);
    fs.mkdirSync(userDestDir, { recursive: true });
    fs.copyFileSync(skillMdSrc, path.join(userDestDir, 'SKILL.md'));

    const manifestSrc = path.join(skillDir, 'JULIUS_SKILL.yaml');
    if (fs.existsSync(manifestSrc)) {
      fs.copyFileSync(manifestSrc, path.join(userDestDir, 'JULIUS_SKILL.yaml'));
    }

    const localJuliusDir = path.join(process.cwd(), '.julius', 'skills', safeName);
    if (fs.existsSync(path.dirname(localJuliusDir))) {
      fs.mkdirSync(localJuliusDir, { recursive: true });
      fs.copyFileSync(skillMdSrc, path.join(localJuliusDir, 'SKILL.md'));
      if (fs.existsSync(manifestSrc)) {
        fs.copyFileSync(manifestSrc, path.join(localJuliusDir, 'JULIUS_SKILL.yaml'));
      }
    }

    return true;
  } catch {
    return false;
  }
}
