import { DesignProfile, ColorToken, ShadowToken, ComponentInfo, ComponentCategory } from '../types';

/**
 * Generate DESIGN.md in Google Stitch / awesome-design-md format.
 * Pure template-driven — no AI.
 */
export function generateDesignMd(profile: DesignProfile, screenshotPath?: string | null): string {
  const sections = [
    generateHeader(profile, screenshotPath),
    generateVisualTheme(profile),
    generateColorPalette(profile),
    generateTypography(profile),
    generateComponentStylings(profile),
    generateLayoutPrinciples(profile),
    generateDepthElevation(profile),
    generateAnimationMotion(profile),
    generateDosAndDonts(profile),
    generateResponsiveBehavior(profile),
    generateAgentPromptGuide(profile),
  ];

  return sections.filter(s => s).join('\n\n---\n\n');
}

// ── Header ────────────────────────────────────────────────────────────

function generateHeader(profile: DesignProfile, screenshotPath?: string | null): string {
  const frameworkList = profile.frameworks.map(f =>
    f.version ? `${f.name} ${f.version}` : f.name
  ).join(' + ');

  const fonts = [...new Set(profile.typography.map(t => t.fontFamily))].filter(f => f);

  // Declare variable header initialized to `# ${profile.projectName} DESIGN.md
  let header = `# ${profile.projectName} DESIGN.md

> Auto-generated design system — reverse-engineered via static analysis by skillui.
> Frameworks: ${frameworkList || 'None detected'}
> Colors: ${profile.colors.length} · Fonts: ${fonts.length} · Components: ${profile.components.length}
> Icon library: ${profile.iconLibrary || 'not detected'} · State: ${profile.stateLibrary || 'not detected'}
> Primary theme: ${profile.designTraits.isDark ? 'dark' : 'light'} · Dark mode toggle: ${profile.designTraits.hasDarkMode ? 'yes' : 'no'} · Motion: ${profile.designTraits.motionStyle}`;

  // Check condition: screenshotPath
  if (screenshotPath) {
    // Execute statement: header += `\n\n## Visual Reference\n\n**Match this design exactly** — study colors, fonts, spacing, and component shapes before writing any UI code.\n\n![${profile.projectName} Homepage](../${screenshotPath})`;
    header += `\n\n## Visual Reference\n\n**Match this design exactly** — study colors, fonts, spacing, and component shapes before writing any UI code.\n\n![${profile.projectName} Homepage](../${screenshotPath})`;
  }

  // Return value header; to caller
  return header;
}

// ── Section 1: Visual Theme & Atmosphere ──────────────────────────────

// Define function generateVisualTheme(profile: DesignProfile)
function generateVisualTheme(profile: DesignProfile): string {
  // Define constant traits set to profile.designTraits;
  const traits = profile.designTraits;
  // Define constant bg set to profile.colors.find(c => c.role === 'background');
  const bg = profile.colors.find(c => c.role === 'background');
  // Define constant accent set to profile.colors.find(c => c.role === 'accent');
  const accent = profile.colors.find(c => c.role === 'accent');
  // Define constant fonts set to [...new Set(profile.typography.map(t => t.fontFamily))].filter(f => f);
  const fonts = [...new Set(profile.typography.map(t => t.fontFamily))].filter(f => f);
  // Define constant isMono set to (f: string) => /mono|consolas|courier|fira code|jetbrains|sf mono|menlo/i.test(f);
  const isMono = (f: string) => /mono|consolas|courier|fira code|jetbrains|sf mono|menlo/i.test(f);
  // Define constant displayFonts set to fonts.filter(f => !isMono(f));
  const displayFonts = fonts.filter(f => !isMono(f));
  // Define constant primaryFont set to displayFonts[0] || fonts[0] || 'sans-serif';
  const primaryFont = displayFonts[0] || fonts[0] || 'sans-serif';
  // Define constant theme set to traits.isDark ? 'dark' : 'light';
  const theme = traits.isDark ? 'dark' : 'light';

  // Execute statement: const lines: string[] = [];
  const lines: string[] = [];

  // Overall vibe
  if (traits.isDark && !traits.hasShadows) {
    // Execute statement: lines.push(`This is a **${theme}-themed** interface with a flat, ${traits.primaryColorTemp} visual language. Elevation is achieved through color and border shifts rather than shadows — a clean, industrial aesthetic.`);
    lines.push(`This is a **${theme}-themed** interface with a flat, ${traits.primaryColorTemp} visual language. Elevation is achieved through color and border shifts rather than shadows — a clean, industrial aesthetic.`);
  // Execute statement: } else if (traits.isDark) {
  } else if (traits.isDark) {
    // Execute statement: lines.push(`This is a **${theme}-themed** interface with a ${traits.primaryColorTemp} tone. Depth is expressed through layered shadows and subtle surface color variation.`);
    lines.push(`This is a **${theme}-themed** interface with a ${traits.primaryColorTemp} tone. Depth is expressed through layered shadows and subtle surface color variation.`);
  // Execute statement: } else {
  } else {
    // Execute statement: lines.push(`This is a **${theme}-themed** interface with a ${traits.primaryColorTemp}, approachable feel. The light background emphasizes content clarity.`);
    lines.push(`This is a **${theme}-themed** interface with a ${traits.primaryColorTemp}, approachable feel. The light background emphasizes content clarity.`);
  }

  // Typography character
  if (displayFonts.length >= 2) {
    // Define constant displayFont set to displayFonts.find(f => f !== primaryFont) || displayFonts[1];
    const displayFont = displayFonts.find(f => f !== primaryFont) || displayFonts[1];
    // Execute statement: lines.push(`Typography pairs **${displayFont}** for display/headings with **${primaryFont}** for body text, creating clear visual hierarchy through type contrast.`);
    lines.push(`Typography pairs **${displayFont}** for display/headings with **${primaryFont}** for body text, creating clear visual hierarchy through type contrast.`);
  // Execute statement: } else {
  } else {
    // Define constant fontDesc set to traits.fontStyle === 'monospace' ? 'technical, developer-focused'
    const fontDesc = traits.fontStyle === 'monospace' ? 'technical, developer-focused'
      // Execute statement: : traits.fontStyle === 'serif' ? 'editorial, refined'
      : traits.fontStyle === 'serif' ? 'editorial, refined'
      // Execute statement: : 'clean, modern';
      : 'clean, modern';
    // Execute statement: lines.push(`Typography uses **${primaryFont}** throughout — a ${fontDesc} choice that maintains consistency.`);
    lines.push(`Typography uses **${primaryFont}** throughout — a ${fontDesc} choice that maintains consistency.`);
  }

  // Spacing + density
  lines.push(`Spacing follows a **${profile.spacing.base}px base grid** (${traits.density} density), with scale: ${profile.spacing.values.slice(0, 8).join(', ')}px.`);

  // Accent + color strategy
  if (accent) {
    // Define constant colorCount set to profile.colors.filter(c => c.role !== 'unknown').length;
    const colorCount = profile.colors.filter(c => c.role !== 'unknown').length;
    // Define constant neutralCount set to profile.colors.filter(c =>
    const neutralCount = profile.colors.filter(c =>
      // Set c.role to == 'background' || c.role === 'surface' || c.role === 'text-primary' || c.role === 'text-muted' || c.role === 'border'
      c.role === 'background' || c.role === 'surface' || c.role === 'text-primary' || c.role === 'text-muted' || c.role === 'border'
    // Execute statement: ).length;
    ).length;

    // Check condition: neutralCount >= 3 && colorCount - neutralCount <= 3
    if (neutralCount >= 3 && colorCount - neutralCount <= 3) {
      // Execute statement: lines.push(`The palette is predominantly monochromatic with **${accent.hex}** as the single accent color — used sparingly for interactive elements and emphasis.`);
      lines.push(`The palette is predominantly monochromatic with **${accent.hex}** as the single accent color — used sparingly for interactive elements and emphasis.`);
    // Execute statement: } else {
    } else {
      // Execute statement: lines.push(`The accent color **${accent.hex}** anchors interactive elements (buttons, links, focus rings).`);
      lines.push(`The accent color **${accent.hex}** anchors interactive elements (buttons, links, focus rings).`);
    }
  }

  // Motion summary
  if (traits.motionStyle === 'expressive') {
    // Execute statement: lines.push('Motion is expressive — spring physics, layout animations, and staggered reveals are part of the visual language.');
    lines.push('Motion is expressive — spring physics, layout animations, and staggered reveals are part of the visual language.');
  // Execute statement: } else if (traits.motionStyle === 'subtle') {
  } else if (traits.motionStyle === 'subtle') {
    // Execute statement: lines.push('Motion is subtle — smooth transitions (150-300ms) ease state changes without drawing attention.');
    lines.push('Motion is subtle — smooth transitions (150-300ms) ease state changes without drawing attention.');
  }

  return `## 1. Visual Theme & Atmosphere

${lines.join(' ')}`;
}

// ── Section 2: Color Palette & Roles ──────────────────────────────────

function generateColorPalette(profile: DesignProfile): string {
  if (profile.colors.length === 0) {
    // Return value `## 2. Color Palette & Roles to caller
    return `## 2. Color Palette & Roles

No colors detected in the project.`;
  }

  // Execute statement: const roleOrder: string[] = ['background', 'surface', 'text-primary', 'text-muted', 'border', 'accent', 'danger', 'success', 'warning', 'info', 'unknown'];
  const roleOrder: string[] = ['background', 'surface', 'text-primary', 'text-muted', 'border', 'accent', 'danger', 'success', 'warning', 'info', 'unknown'];

  // Define constant sorted set to [...profile.colors].sort((a, b) => {
  const sorted = [...profile.colors].sort((a, b) => {
    // Define constant ai set to roleOrder.indexOf(a.role);
    const ai = roleOrder.indexOf(a.role);
    // Define constant bi set to roleOrder.indexOf(b.role);
    const bi = roleOrder.indexOf(b.role);
    // Return value ai - bi; to caller
    return ai - bi;
  });

  // Declare variable table initialized to '| Token | Hex | Role | Use |\n|---|---|---|---|\n';
  let table = '| Token | Hex | Role | Use |\n|---|---|---|---|\n';
  // Execute statement: for (const color of sorted) {
  for (const color of sorted) {
    // Define constant name set to color.name || color.role;
    const name = color.name || color.role;
    // Define constant roleDesc set to getColorRoleDescription(color.role);
    const roleDesc = getColorRoleDescription(color.role);
    // Execute statement: table += `| ${name} | \`${color.hex}\` | ${color.role} | ${roleDesc} |\n`;
    table += `| ${name} | \`${color.hex}\` | ${color.role} | ${roleDesc} |\n`;
  }

  // Dark/light mode variable mapping
  let modeSection = '';
  // Check condition: profile.darkModeVars.length > 0
  if (profile.darkModeVars.length > 0) {
    // Set modeSection to '\n### Dark Mode Token Mapping\n\n';
    modeSection = '\n### Dark Mode Token Mapping\n\n';
    // Execute statement: modeSection += '| Variable | Light | Dark |\n|---|---|---|\n';
    modeSection += '| Variable | Light | Dark |\n|---|---|---|\n';
    // Execute statement: for (const v of profile.darkModeVars.slice(0, 20)) {
    for (const v of profile.darkModeVars.slice(0, 20)) {
      // Execute statement: modeSection += `| \`${v.variable}\` | \`${v.lightValue}\` | \`${v.darkValue}\` |\n`;
      modeSection += `| \`${v.variable}\` | \`${v.lightValue}\` | \`${v.darkValue}\` |\n`;
    }
  }

  // CSS variable tokens
  const modeVars = profile.cssVariables.filter(v =>
    // Execute statement: /foreground|background|primary|secondary|muted|accent|destructive|border|card|popover/i.test(v.name) &&
    /foreground|background|primary|secondary|muted|accent|destructive|border|card|popover/i.test(v.name) &&
    // Execute statement: v.value.length < 40
    v.value.length < 40
  );

  // Declare variable cssVarSection initialized to '';
  let cssVarSection = '';
  // Check condition: modeVars.length > 0
  if (modeVars.length > 0) {
    // Set cssVarSection to '\n### CSS Variable Tokens\n\n';
    cssVarSection = '\n### CSS Variable Tokens\n\n';
    cssVarSection += '```css\n';
    // Execute statement: for (const v of modeVars.slice(0, 20)) {
    for (const v of modeVars.slice(0, 20)) {
      // Execute statement: cssVarSection += `${v.name}: ${v.value};\n`;
      cssVarSection += `${v.name}: ${v.value};\n`;
    }
    cssVarSection += '```\n';
  }

  return `## 2. Color Palette & Roles

${table}${modeSection}${cssVarSection}`;
}

function getColorRoleDescription(role: string): string {
  const descriptions: Record<string, string> = {
    'background': 'Page background, darkest surface',
    'surface': 'Card and panel backgrounds',
    'text-primary': 'Headings and body text',
    'text-muted': 'Captions, placeholders, secondary info',
    'accent': 'CTAs, links, focus rings, active states',
    'border': 'Dividers, card borders, outlines',
    'danger': 'Error states, destructive actions',
    'success': 'Success states, positive indicators',
    'warning': 'Warning states, caution indicators',
    'info': 'Informational highlights',
    'unknown': 'Palette color',
  };
  return descriptions[role] || 'Palette color';
}

// ── Section 3: Typography Rules ───────────────────────────────────────

function generateTypography(profile: DesignProfile): string {
  if (profile.typography.length === 0) {
    // Return value `## 3. Typography Rules to caller
    return `## 3. Typography Rules

No typography tokens detected.`;
  }

  // Define constant fonts set to [...new Set(profile.typography.map(t => t.fontFamily))].filter(f => f);
  const fonts = [...new Set(profile.typography.map(t => t.fontFamily))].filter(f => f);
  // Declare variable fontStack initialized to '';
  let fontStack = '';
  // Check condition: fonts.length > 0
  if (fonts.length > 0) {
    // Set fontStack to '**Font Stack:**\n';
    fontStack = '**Font Stack:**\n';
    // Execute statement: for (const font of fonts) {
    for (const font of fonts) {
      // Define constant roles set to profile.typography.filter(t => t.fontFamily === font).map(t => formatTypographyRole(t.role));
      const roles = profile.typography.filter(t => t.fontFamily === font).map(t => formatTypographyRole(t.role));
      // Execute statement: fontStack += `- **${font}** — ${roles.join(', ')}\n`;
      fontStack += `- **${font}** — ${roles.join(', ')}\n`;
    }
    // Execute statement: fontStack += '\n';
    fontStack += '\n';
  }

  // Font source declarations
  let fontSources = '';
  // Check condition: profile.fontSources.length > 0
  if (profile.fontSources.length > 0) {
    fontSources = '**Font Sources:**\n\n```css\n';
    // Define constant families set to [...new Set(profile.fontSources.map(fs => fs.family))];
    const families = [...new Set(profile.fontSources.map(fs => fs.family))];
    // Collect weights actually used in the type scale
    const usedWeights = new Set(profile.typography.map(t => t.fontWeight || '400'));
    // Execute statement: usedWeights.add('400');
    usedWeights.add('400');
    // Execute statement: usedWeights.add('700');
    usedWeights.add('700');
    // Execute statement: for (const family of families) {
    for (const family of families) {
      // Define constant sources set to profile.fontSources.filter(fs => fs.family === family);
      const sources = profile.fontSources.filter(fs => fs.family === family);
      // Check for variable fonts first
      const variableSource = sources.find(s => s.weight === 'variable');
      // Check condition: variableSource
      if (variableSource) {
        // Execute statement: fontSources += `@font-face {\n  font-family: "${family}";\n  src: url("${variableSource.src}")${variableSource.format ? ` format("${variableSource.format}")` : ''};\n  font-weight: 100 900;\n}\n`;
        fontSources += `@font-face {\n  font-family: "${family}";\n  src: url("${variableSource.src}")${variableSource.format ? ` format("${variableSource.format}")` : ''};\n  font-weight: 100 900;\n}\n`;
      // Execute statement: } else {
      } else {
        // Define constant byWeight set to new Map<string, typeof sources[0]>();
        const byWeight = new Map<string, typeof sources[0]>();
        // Execute statement: for (const src of sources) {
        for (const src of sources) {
          // Define constant w set to src.weight || '400';
          const w = src.weight || '400';
          // Check condition: !usedWeights.has(w)
          if (!usedWeights.has(w)) continue;
          // Define constant existing set to byWeight.get(w);
          const existing = byWeight.get(w);
          // Check condition: !existing || (src.format === 'woff2' && existing.format !== 'woff2')
          if (!existing || (src.format === 'woff2' && existing.format !== 'woff2')) {
            // Execute statement: byWeight.set(w, src);
            byWeight.set(w, src);
          }
        }
        // Check condition: byWeight.size === 0 && sources.length > 0
        if (byWeight.size === 0 && sources.length > 0) {
          // Execute statement: byWeight.set(sources[0].weight || '400', sources[0]);
          byWeight.set(sources[0].weight || '400', sources[0]);
        }
        // Execute statement: for (const [weight, src] of byWeight) {
        for (const [weight, src] of byWeight) {
          // Execute statement: fontSources += `@font-face {\n  font-family: "${family}";\n  src: url("${src.src}")${src.format ? ` format("${src.format}")` : ''};\n  font-weight: ${weight};\n}\n`;
          fontSources += `@font-face {\n  font-family: "${family}";\n  src: url("${src.src}")${src.format ? ` format("${src.format}")` : ''};\n  font-weight: ${weight};\n}\n`;
        }
      }
    }
    fontSources += '```\n\n';
  }

  // Declare variable table initialized to '| Role | Font | Size | Weight |\n|---|---|---|---|\n';
  let table = '| Role | Font | Size | Weight |\n|---|---|---|---|\n';
  // Execute statement: for (const t of profile.typography) {
  for (const t of profile.typography) {
    // Define constant roleName set to formatTypographyRole(t.role);
    const roleName = formatTypographyRole(t.role);
    // Execute statement: table += `| ${roleName} | ${t.fontFamily} | ${t.fontSize || 'inherit'} | ${t.fontWeight || 'inherit'} |\n`;
    table += `| ${roleName} | ${t.fontFamily} | ${t.fontSize || 'inherit'} | ${t.fontWeight || 'inherit'} |\n`;
  }

  // Define constant isMono set to (f: string) => /mono|consolas|courier|fira code|jetbrains|sf mono|menlo/i.test(f);
  const isMono = (f: string) => /mono|consolas|courier|fira code|jetbrains|sf mono|menlo/i.test(f);
  // Define constant displayFonts set to fonts.filter(f => !isMono(f));
  const displayFonts = fonts.filter(f => !isMono(f));

  // Declare variable rules initialized to '\n**Typographic Rules:**\n';
  let rules = '\n**Typographic Rules:**\n';
  // Check condition: displayFonts.length <= 1
  if (displayFonts.length <= 1) {
    // Execute statement: rules += `- Use **${displayFonts[0] || fonts[0]}** for all text — do not mix font families\n`;
    rules += `- Use **${displayFonts[0] || fonts[0]}** for all text — do not mix font families\n`;
  // Execute statement: } else {
  } else {
    // Execute statement: rules += `- Limit to ${fonts.length} font families max per screen\n`;
    rules += `- Limit to ${fonts.length} font families max per screen\n`;
    // Execute statement: rules += `- Use **${displayFonts[0]}** for body/UI text, **${displayFonts[1]}** for display/headings\n`;
    rules += `- Use **${displayFonts[0]}** for body/UI text, **${displayFonts[1]}** for display/headings\n`;
  }
  // Execute statement: rules += '- Maintain consistent hierarchy: no more than 3-4 font sizes per screen\n';
  rules += '- Maintain consistent hierarchy: no more than 3-4 font sizes per screen\n';
  // Execute statement: rules += '- Headings use bold (600-700), body uses regular (400)\n';
  rules += '- Headings use bold (600-700), body uses regular (400)\n';
  // Execute statement: rules += '- Line height: 1.5 for body text, 1.2 for headings\n';
  rules += '- Line height: 1.5 for body text, 1.2 for headings\n';
  // Execute statement: rules += '- Use color and opacity for secondary hierarchy, not additional font sizes\n';
  rules += '- Use color and opacity for secondary hierarchy, not additional font sizes\n';

  return `## 3. Typography Rules

${fontStack}${fontSources}${table}${rules}`;
}

function formatTypographyRole(role: string): string {
  return role.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

// ── Section 4: Component Stylings ─────────────────────────────────────

function generateComponentStylings(profile: DesignProfile): string {
  if (profile.components.length === 0) {
    // Return value `## 4. Component Stylings to caller
    return `## 4. Component Stylings

No components detected. Scan \`src/components/\` or \`components/\` to populate this section.`;
  }

  // Declare variable content initialized to '';
  let content = '';

  // Group by category
  const categories: ComponentCategory[] = ['layout', 'navigation', 'data-display', 'data-input', 'feedback', 'overlay', 'typography', 'media', 'other'];
  // Execute statement: const categoryNames: Record<ComponentCategory, string> = {
  const categoryNames: Record<ComponentCategory, string> = {
    // Execute statement: 'layout': 'Layout',
    'layout': 'Layout',
    // Execute statement: 'navigation': 'Navigation',
    'navigation': 'Navigation',
    // Execute statement: 'data-display': 'Data Display',
    'data-display': 'Data Display',
    // Execute statement: 'data-input': 'Data Input',
    'data-input': 'Data Input',
    // Execute statement: 'feedback': 'Feedback',
    'feedback': 'Feedback',
    // Execute statement: 'overlay': 'Overlay',
    'overlay': 'Overlay',
    // Execute statement: 'typography': 'Typography',
    'typography': 'Typography',
    // Execute statement: 'media': 'Media',
    'media': 'Media',
    // Execute statement: 'other': 'Other',
    'other': 'Other',
  };

  // Execute statement: for (const cat of categories) {
  for (const cat of categories) {
    // Define constant comps set to profile.components.filter(c => c.category === cat);
    const comps = profile.components.filter(c => c.category === cat);
    // Check condition: comps.length === 0
    if (comps.length === 0) continue;

    // Execute statement: content += `### ${categoryNames[cat]} (${comps.length})\n\n`;
    content += `### ${categoryNames[cat]} (${comps.length})\n\n`;

    // Execute statement: for (const comp of comps.slice(0, 8)) {
    for (const comp of comps.slice(0, 8)) {
      // Execute statement: content += `**${comp.name}** — \`${comp.filePath}\`\n`;
      content += `**${comp.name}** — \`${comp.filePath}\`\n`;

      // Check condition: comp.variants.length > 0
      if (comp.variants.length > 0) {
        // Execute statement: content += `- Variants: ${comp.variants.map(v => `\`${v}\``).join(', ')}\n`;
        content += `- Variants: ${comp.variants.map(v => `\`${v}\``).join(', ')}\n`;
      }

      // Check condition: comp.props.length > 0
      if (comp.props.length > 0) {
        // Execute statement: content += `- Props: ${comp.props.slice(0, 8).map(p => `\`${p}\``).join(', ')}`;
        content += `- Props: ${comp.props.slice(0, 8).map(p => `\`${p}\``).join(', ')}`;
        if (comp.props.length > 8) content += ` (+${comp.props.length - 8} more)`;
        content += '\n';
      }

      const visualProps = extractVisualProperties(comp);
      if (visualProps.length > 0) {
        content += `- Key Styles: ${visualProps.join(', ')}\n`;
      }

      if (comp.hasAnimation) {
        content += `- Animation: ${comp.animationDetails.slice(0, 3).join(', ')}\n`;
      }

      if (comp.statePatterns.length > 0) {
        content += `- State: ${comp.statePatterns.join(', ')}\n`;
      }

      // Show JSX snippet (compact)
      if (comp.jsxSnippet) {
        const cleanSnippet = comp.jsxSnippet.split('\n').slice(0, 12).join('\n').trim();
        if (cleanSnippet) {
          content += `\n\`\`\`tsx\n${cleanSnippet}\n\`\`\`\n`;
        }
      }

      content += '\n';
    }

    if (comps.length > 8) {
      content += `*...and ${comps.length - 8} more ${categoryNames[cat].toLowerCase()} components.*\n\n`;
    }
  }

  // Return value `## 4. Component Stylings to caller
  return `## 4. Component Stylings

${content}`;
}

// Define function extractVisualProperties(comp: ComponentInfo)
function extractVisualProperties(comp: ComponentInfo): string[] {
  // Execute statement: const props: string[] = [];
  const props: string[] = [];
  // Define constant tp set to comp.tailwindPatterns;
  const tp = comp.tailwindPatterns;

  // Pick the most representative class from each category
  if (tp.borders.length > 0) {
    // Define constant rounded set to tp.borders.find(c => c.startsWith('rounded'));
    const rounded = tp.borders.find(c => c.startsWith('rounded'));
    // Check condition: rounded) props.push(`\`${rounded}\``
    if (rounded) props.push(`\`${rounded}\``);
    // Define constant borderColor set to tp.borders.find(c => c.startsWith('border-') && !c.startsWith('border-t') && !c.startsWith('border-b'));
    const borderColor = tp.borders.find(c => c.startsWith('border-') && !c.startsWith('border-t') && !c.startsWith('border-b'));
    // Check condition: borderColor) props.push(`\`${borderColor}\``
    if (borderColor) props.push(`\`${borderColor}\``);
  }

  // Check condition: tp.backgrounds.length > 0
  if (tp.backgrounds.length > 0) {
    // Execute statement: props.push(`\`${tp.backgrounds[0]}\``);
    props.push(`\`${tp.backgrounds[0]}\``);
  }

  // Check condition: tp.spacing.length > 0
  if (tp.spacing.length > 0) {
    // Execute statement: props.push(`\`${tp.spacing[0]}\``);
    props.push(`\`${tp.spacing[0]}\``);
  }

  // Check condition: tp.typography.length > 0
  if (tp.typography.length > 0) {
    // Define constant textSize set to tp.typography.find(c => /text-(xs|sm|base|lg|xl|2xl|3xl|4xl)/.test(c));
    const textSize = tp.typography.find(c => /text-(xs|sm|base|lg|xl|2xl|3xl|4xl)/.test(c));
    // Check condition: textSize) props.push(`\`${textSize}\``
    if (textSize) props.push(`\`${textSize}\``);
    // Define constant font set to tp.typography.find(c => c.startsWith('font-'));
    const font = tp.typography.find(c => c.startsWith('font-'));
    // Check condition: font) props.push(`\`${font}\``
    if (font) props.push(`\`${font}\``);
  }

  // Check condition: tp.effects.length > 0
  if (tp.effects.length > 0) {
    // Execute statement: props.push(`\`${tp.effects[0]}\``);
    props.push(`\`${tp.effects[0]}\``);
  }

  // Check condition: tp.interactive.length > 0
  if (tp.interactive.length > 0) {
    // Execute statement: props.push(`\`${tp.interactive[0]}\``);
    props.push(`\`${tp.interactive[0]}\``);
  }

  // Return value props; to caller
  return props;
}

// ── Section 5: Layout Principles ──────────────────────────────────────

// Define function generateLayoutPrinciples(profile: DesignProfile)
function generateLayoutPrinciples(profile: DesignProfile): string {
  // Define constant sp set to profile.spacing;
  const sp = profile.spacing;
  // Define constant scaleStr set to sp.values.slice(0, 12).join(', ');
  const scaleStr = sp.values.slice(0, 12).join(', ');

  // Declare variable content initialized to `- **Base spacing unit:** ${sp.base}px\n`;
  let content = `- **Base spacing unit:** ${sp.base}px\n`;
  // Execute statement: content += `- **Spacing scale:** ${scaleStr}\n`;
  content += `- **Spacing scale:** ${scaleStr}\n`;

  // Border radius
  if (profile.borderRadius.length > 0) {
    // Define constant radii set to profile.borderRadius.filter(r => !r.includes('9999'));
    const radii = profile.borderRadius.filter(r => !r.includes('9999'));
    // Check condition: radii.length > 0
    if (radii.length > 0) {
      // Execute statement: content += `- **Border radius:** ${radii.join(', ')}\n`;
      content += `- **Border radius:** ${radii.join(', ')}\n`;
    }
  }

  // Container
  if (profile.containerMaxWidth) {
    // Execute statement: content += `- **Max content width:** ${profile.containerMaxWidth}\n`;
    content += `- **Max content width:** ${profile.containerMaxWidth}\n`;
  }

  // Grid usage from component classes
  const gridClasses = new Set<string>();
  // Execute statement: for (const comp of profile.components) {
  for (const comp of profile.components) {
    // Execute statement: for (const cls of comp.tailwindPatterns.layout) {
    for (const cls of comp.tailwindPatterns.layout) {
      // Check condition: /grid-cols-\d+|col-span|columns-\d+/.test(cls)
      if (/grid-cols-\d+|col-span|columns-\d+/.test(cls)) {
        // Execute statement: gridClasses.add(cls);
        gridClasses.add(cls);
      }
    }
  }

  // Check condition: gridClasses.size > 0
  if (gridClasses.size > 0) {
    // Execute statement: content += `- **Grid usage:** ${Array.from(gridClasses).slice(0, 5).map(c => `\`${c}\``).join(', ')}\n`;
    content += `- **Grid usage:** ${Array.from(gridClasses).slice(0, 5).map(c => `\`${c}\``).join(', ')}\n`;
  }

  // Define constant hasTailwind set to profile.frameworks.some(f => f.id === 'tailwind');
  const hasTailwind = profile.frameworks.some(f => f.id === 'tailwind');
  // Check condition: hasTailwind
  if (hasTailwind) {
    // Execute statement: content += `- **Container:** Tailwind \`container\` class with responsive padding\n`;
    content += `- **Container:** Tailwind \`container\` class with responsive padding\n`;
  }

  // Spacing philosophy
  content += `\n**Spacing as Meaning:**\n`;
  // Execute statement: content += `| Spacing | Use |\n|---|---|\n`;
  content += `| Spacing | Use |\n|---|---|\n`;
  // Check condition: sp.base <= 4
  if (sp.base <= 4) {
    // Execute statement: content += `| ${sp.base}-${sp.base * 2}px | Tight: related items within a group |\n`;
    content += `| ${sp.base}-${sp.base * 2}px | Tight: related items within a group |\n`;
    // Execute statement: content += `| ${sp.base * 3}-${sp.base * 4}px | Medium: between groups |\n`;
    content += `| ${sp.base * 3}-${sp.base * 4}px | Medium: between groups |\n`;
    // Execute statement: content += `| ${sp.base * 6}-${sp.base * 8}px | Wide: between sections |\n`;
    content += `| ${sp.base * 6}-${sp.base * 8}px | Wide: between sections |\n`;
    // Execute statement: content += `| ${sp.base * 12}px+ | Vast: major section breaks |\n`;
    content += `| ${sp.base * 12}px+ | Vast: major section breaks |\n`;
  // Execute statement: } else {
  } else {
    // Execute statement: content += `| ${sp.base / 2}-${sp.base}px | Tight: related items within a group |\n`;
    content += `| ${sp.base / 2}-${sp.base}px | Tight: related items within a group |\n`;
    // Execute statement: content += `| ${sp.base * 2}px | Medium: between groups |\n`;
    content += `| ${sp.base * 2}px | Medium: between groups |\n`;
    // Execute statement: content += `| ${sp.base * 3}-${sp.base * 4}px | Wide: between sections |\n`;
    content += `| ${sp.base * 3}-${sp.base * 4}px | Wide: between sections |\n`;
    // Execute statement: content += `| ${sp.base * 6}px+ | Vast: major section breaks |\n`;
    content += `| ${sp.base * 6}px+ | Vast: major section breaks |\n`;
  }

  return `## 5. Layout Principles

${content}`;
}

// ── Section 6: Depth & Elevation ──────────────────────────────────────

function generateDepthElevation(profile: DesignProfile): string {
  if (profile.shadows.length === 0) {
    let content = '';

    if (profile.designTraits.isDark) {
      content += 'No box-shadow values detected. The design uses a **flat visual style** — elevation is conveyed through background color shifts and borders rather than shadows.\n\n';
      content += '**Elevation Strategy:**\n';
      content += '| Level | Technique | Use |\n|---|---|---|\n';
      content += '| 0 — Base | Background color | Page background |\n';
      content += '| 1 — Raised | Lighter surface + subtle border | Cards, panels |\n';
      content += '| 2 — Floating | Even lighter surface + stronger border | Dropdowns, popovers |\n';
      content += '| 3 — Overlay | Backdrop + modal surface | Modals, dialogs |\n';
    } else {
      content += 'No box-shadow values detected. The design appears to use a flat visual style.\n';
    }

    // z-index
    if (profile.zIndexScale.length > 0) {
      content += `\n**Z-Index Scale:** \`${profile.zIndexScale.join(', ')}\`\n`;
    }

    // Return value `## 6. Depth & Elevation to caller
    return `## 6. Depth & Elevation

${content}`;
  }

  // Declare variable content initialized to '';
  let content = '';
  // Execute statement: const levels: Record<string, ShadowToken[]> = {};
  const levels: Record<string, ShadowToken[]> = {};
  // Execute statement: for (const shadow of profile.shadows) {
  for (const shadow of profile.shadows) {
    // Check condition: !levels[shadow.level]
    if (!levels[shadow.level]) levels[shadow.level] = [];
    // Execute statement: levels[shadow.level].push(shadow);
    levels[shadow.level].push(shadow);
  }

  // Execute statement: const levelDescriptions: Record<string, string> = {
  const levelDescriptions: Record<string, string> = {
    // Define property flat with type 'Flat — subtle depth hints',
    flat: 'Flat — subtle depth hints',
    // Define property raised with type 'Raised — cards, buttons, interactive elements',
    raised: 'Raised — cards, buttons, interactive elements',
    // Define property floating with type 'Floating — dropdowns, popovers, modals',
    floating: 'Floating — dropdowns, popovers, modals',
    // Define property overlay with type 'Overlay — full-screen overlays, top-level dialogs',
    overlay: 'Overlay — full-screen overlays, top-level dialogs',
  };

  // Execute statement: for (const [level, shadows] of Object.entries(levels)) {
  for (const [level, shadows] of Object.entries(levels)) {
    // Execute statement: content += `### ${levelDescriptions[level] || level}\n\n`;
    content += `### ${levelDescriptions[level] || level}\n\n`;
    // Execute statement: for (const s of shadows.slice(0, 3)) {
    for (const s of shadows.slice(0, 3)) {
      // Define constant label set to s.name ? `**${s.name}:** ` : '';
      const label = s.name ? `**${s.name}:** ` : '';
      // Execute statement: content += `- ${label}\`${s.value}\`\n`;
      content += `- ${label}\`${s.value}\`\n`;
    }
    // Execute statement: content += '\n';
    content += '\n';
  }

  // z-index
  if (profile.zIndexScale.length > 0) {
    // Execute statement: content += `### Z-Index Scale\n\n`;
    content += `### Z-Index Scale\n\n`;
    // Execute statement: content += `\`${profile.zIndexScale.join(', ')}\`\n\n`;
    content += `\`${profile.zIndexScale.join(', ')}\`\n\n`;
  }

  return `## 6. Depth & Elevation

${content}`;
}

// ── Section 7: Animation & Motion ─────────────────────────────────────

function generateAnimationMotion(profile: DesignProfile): string {
  if (!profile.designTraits.hasAnimations && profile.designTraits.motionStyle === 'none') {
    return ''; // Skip section entirely
  }

  let content = '';

  if (profile.designTraits.motionStyle === 'expressive') {
    content += 'This project uses **expressive motion**. Animations are an integral part of the experience.\n\n';
  } else {
    content += 'This project uses **subtle motion**. Transitions smooth state changes without demanding attention.\n\n';
  }

  // Framer Motion
  const hasFramerMotion = profile.animations.some(a => a.type === 'framer-motion');
  if (hasFramerMotion) {
    content += '### Framer Motion Patterns\n\n';
    // Execute statement: content += '```tsx\n';
    content += '```tsx\n';
    content += '// Standard enter animation\n';
    content += '<motion.div\n';
    content += '  initial={{ opacity: 0, y: 8 }}\n';
    content += '  animate={{ opacity: 1, y: 0 }}\n';
    content += '  transition={{ duration: 0.3, ease: "easeOut" }}\n';
    content += '/>\n\n';
    content += '// List stagger\n';
    content += 'const container = {\n';
    content += '  hidden: {},\n';
    content += '  show: { transition: { staggerChildren: 0.05 } }\n';
    content += '}\n';
    content += 'const item = {\n';
    content += '  hidden: { opacity: 0, y: 8 },\n';
    content += '  show: { opacity: 1, y: 0 }\n';
    content += '}\n';
    // Execute statement: content += '```\n\n';
    content += '```\n\n';
  }

  // CSS keyframes
  const keyframes = profile.animations.filter(a => a.type === 'css-keyframe');
  if (keyframes.length > 0) {
    content += '### CSS Animations\n\n';
    for (const kf of keyframes.slice(0, 8)) {
      content += `- \`@keyframes ${kf.name}\`\n`;
    }
    content += '\n';
  }

  // Animation components
  const animatedComps = profile.components.filter(c => c.hasAnimation).slice(0, 5);
  if (animatedComps.length > 0) {
    content += '### Animated Components\n\n';
    for (const comp of animatedComps) {
      content += `- **${comp.name}**: ${comp.animationDetails.slice(0, 3).join(', ')}\n`;
    }
    content += '\n';
  }

  content += '### Motion Guidelines\n\n';
  content += '- Duration: 150-300ms for micro-interactions, 300-500ms for page transitions\n';
  content += '- Easing: `ease-out` for enters, `ease-in` for exits\n';
  content += '- Always respect `prefers-reduced-motion`\n';

  // Return value `## 7. Animation & Motion to caller
  return `## 7. Animation & Motion

${content}`;
}

// ── Section 8: Do's and Don'ts ────────────────────────────────────────

// Define function generateDosAndDonts(profile: DesignProfile)
function generateDosAndDonts(profile: DesignProfile): string {
  // Execute statement: const dos: string[] = [];
  const dos: string[] = [];
  // Execute statement: const donts: string[] = [];
  const donts: string[] = [];
  // Define constant traits set to profile.designTraits;
  const traits = profile.designTraits;

  // Define constant accent set to profile.colors.find(c => c.role === 'accent');
  const accent = profile.colors.find(c => c.role === 'accent');
  // Define constant bg set to profile.colors.find(c => c.role === 'background');
  const bg = profile.colors.find(c => c.role === 'background');
  // Define constant fonts set to [...new Set(profile.typography.map(t => t.fontFamily))];
  const fonts = [...new Set(profile.typography.map(t => t.fontFamily))];
  // Define constant isMono set to (f: string) => /mono|consolas|courier|fira code|jetbrains|sf mono|menlo/i.test(f);
  const isMono = (f: string) => /mono|consolas|courier|fira code|jetbrains|sf mono|menlo/i.test(f);
  // Define constant dFonts set to fonts.filter(f => !isMono(f));
  const dFonts = fonts.filter(f => !isMono(f));

  // Check condition: accent
  if (accent) {
    // Execute statement: dos.push(`Use \`${accent.hex}\` for interactive elements (buttons, links, focus rings)`);
    dos.push(`Use \`${accent.hex}\` for interactive elements (buttons, links, focus rings)`);
  }
  // Check condition: bg
  if (bg) {
    // Execute statement: dos.push(`Use \`${bg.hex}\` as the primary page background`);
    dos.push(`Use \`${bg.hex}\` as the primary page background`);
  }

  // Execute statement: donts.push("Don't introduce colors outside this palette — extend the design tokens first");
  donts.push("Don't introduce colors outside this palette — extend the design tokens first");

  // Check condition: dFonts.length <= 1 && dFonts[0]
  if (dFonts.length <= 1 && dFonts[0]) {
    // Execute statement: dos.push(`Use **${dFonts[0]}** for all UI text`);
    dos.push(`Use **${dFonts[0]}** for all UI text`);
    // Execute statement: donts.push(`Don't mix font families — use ${dFonts[0]} consistently`);
    donts.push(`Don't mix font families — use ${dFonts[0]} consistently`);
  // Execute statement: } else if (dFonts.length >= 2) {
  } else if (dFonts.length >= 2) {
    // Execute statement: dos.push(`Pair **${dFonts[0]}** (body) with **${dFonts[1]}** (display) — these are the only allowed fonts`);
    dos.push(`Pair **${dFonts[0]}** (body) with **${dFonts[1]}** (display) — these are the only allowed fonts`);
    // Execute statement: donts.push(`Don't introduce additional font families beyond ${fonts.join(' and ')}`);
    donts.push(`Don't introduce additional font families beyond ${fonts.join(' and ')}`);
  }

  // Execute statement: dos.push(`Follow the **${profile.spacing.base}px** spacing grid for all margins, padding, and gaps`);
  dos.push(`Follow the **${profile.spacing.base}px** spacing grid for all margins, padding, and gaps`);
  // Execute statement: donts.push(`Don't use arbitrary spacing values — stick to multiples of ${profile.spacing.base}px`);
  donts.push(`Don't use arbitrary spacing values — stick to multiples of ${profile.spacing.base}px`);

  // Check condition: !traits.hasShadows
  if (!traits.hasShadows) {
    // Execute statement: dos.push('Use border and background shifts for elevation — not shadows');
    dos.push('Use border and background shifts for elevation — not shadows');
    // Execute statement: donts.push("Don't add box-shadow — this design system uses flat elevation");
    donts.push("Don't add box-shadow — this design system uses flat elevation");
  // Execute statement: } else {
  } else {
    // Execute statement: dos.push('Use the defined shadow tokens for elevation — see Section 6');
    dos.push('Use the defined shadow tokens for elevation — see Section 6');
    // Execute statement: donts.push("Don't create custom box-shadow values outside the system tokens");
    donts.push("Don't create custom box-shadow values outside the system tokens");
  }

  // Check condition: !traits.hasGradients
  if (!traits.hasGradients) {
    // Execute statement: donts.push("Don't use gradients — the design uses solid colors only");
    donts.push("Don't use gradients — the design uses solid colors only");
  }

  // Check condition: profile.borderRadius.length > 0
  if (profile.borderRadius.length > 0) {
    // Execute statement: dos.push(`Use border-radius from the scale: ${profile.borderRadius.filter(r => !r.includes('9999')).slice(0, 5).join(', ')}`);
    dos.push(`Use border-radius from the scale: ${profile.borderRadius.filter(r => !r.includes('9999')).slice(0, 5).join(', ')}`);
    // Execute statement: donts.push(`Don't use arbitrary border-radius values — pick from the defined scale`);
    donts.push(`Don't use arbitrary border-radius values — pick from the defined scale`);
  }

  // Check condition: profile.components.length > 0
  if (profile.components.length > 0) {
    // Execute statement: dos.push('Reuse existing components from Section 4 before creating new ones');
    dos.push('Reuse existing components from Section 4 before creating new ones');
    // Execute statement: donts.push("Don't duplicate component patterns — check Section 4 first");
    donts.push("Don't duplicate component patterns — check Section 4 first");
  }

  // Check condition: profile.iconLibrary
  if (profile.iconLibrary) {
    // Execute statement: dos.push(`Use **${profile.iconLibrary}** for all icons`);
    dos.push(`Use **${profile.iconLibrary}** for all icons`);
    // Execute statement: donts.push("Don't mix icon libraries — consistency matters");
    donts.push("Don't mix icon libraries — consistency matters");
  }

  // Check condition: profile.antiPatterns.includes('no-blur')
  if (profile.antiPatterns.includes('no-blur')) {
    // Execute statement: donts.push("Don't use backdrop-blur or blur effects");
    donts.push("Don't use backdrop-blur or blur effects");
  }

  // Check condition: profile.designTraits.hasDarkMode
  if (profile.designTraits.hasDarkMode) {
    // Execute statement: dos.push('Always use CSS variables for colors — never hardcode hex');
    dos.push('Always use CSS variables for colors — never hardcode hex');
    // Execute statement: dos.push('Test both light and dark modes for contrast');
    dos.push('Test both light and dark modes for contrast');
  }

  // Declare variable content initialized to "### Do's\n\n";
  let content = "### Do's\n\n";
  // Execute statement: for (const d of dos) content += `- ${d}\n`;
  for (const d of dos) content += `- ${d}\n`;

  // Execute statement: content += "\n### Don'ts\n\n";
  content += "\n### Don'ts\n\n";
  // Execute statement: for (const d of donts) content += `- ${d}\n`;
  for (const d of donts) content += `- ${d}\n`;

  // Detected anti-patterns
  const explicitAntiPatterns: string[] = [];
  // Check condition: profile.antiPatterns.includes('no-shadows')) explicitAntiPatterns.push('No box-shadow on any element'
  if (profile.antiPatterns.includes('no-shadows')) explicitAntiPatterns.push('No box-shadow on any element');
  // Check condition: profile.antiPatterns.includes('no-gradients')) explicitAntiPatterns.push('No gradient backgrounds'
  if (profile.antiPatterns.includes('no-gradients')) explicitAntiPatterns.push('No gradient backgrounds');
  // Check condition: profile.antiPatterns.includes('no-blur')) explicitAntiPatterns.push('No blur or backdrop-blur effects'
  if (profile.antiPatterns.includes('no-blur')) explicitAntiPatterns.push('No blur or backdrop-blur effects');
  // Check condition: profile.antiPatterns.includes('no-zebra-striping')) explicitAntiPatterns.push('No zebra striping on tables/lists'
  if (profile.antiPatterns.includes('no-zebra-striping')) explicitAntiPatterns.push('No zebra striping on tables/lists');

  // Check condition: explicitAntiPatterns.length >= 2
  if (explicitAntiPatterns.length >= 2) {
    // Execute statement: content += '\n### Anti-Patterns (detected from codebase)\n\n';
    content += '\n### Anti-Patterns (detected from codebase)\n\n';
    // Execute statement: for (const ap of explicitAntiPatterns) {
    for (const ap of explicitAntiPatterns) {
      // Execute statement: content += `- ${ap}\n`;
      content += `- ${ap}\n`;
    }
  }

  return `## 8. Do's and Don'ts

${content}`;
}

// ── Section 9: Responsive Behavior ────────────────────────────────────

function generateResponsiveBehavior(profile: DesignProfile): string {
  if (profile.breakpoints.length === 0) {
    // Return value `## 9. Responsive Behavior to caller
    return `## 9. Responsive Behavior

No breakpoints detected. Consider adding responsive breakpoints to the design system.`;
  }

  // Declare variable table initialized to '| Name | Value | Source |\n|---|---|---|\n';
  let table = '| Name | Value | Source |\n|---|---|---|\n';
  // Execute statement: for (const bp of profile.breakpoints) {
  for (const bp of profile.breakpoints) {
    // Execute statement: table += `| ${bp.name} | ${bp.value} | ${bp.source} |\n`;
    table += `| ${bp.name} | ${bp.value} | ${bp.source} |\n`;
  }

  // Define constant hasTailwind set to profile.frameworks.some(f => f.id === 'tailwind');
  const hasTailwind = profile.frameworks.some(f => f.id === 'tailwind');
  // Declare variable content initialized to table;
  let content = table;

  // Check condition: hasTailwind
  if (hasTailwind) {
    // Execute statement: content += `\n**Approach:** Mobile-first using Tailwind responsive prefixes (\`sm:\`, \`md:\`, \`lg:\`, \`xl:\`, \`2xl:\`).\n`;
    content += `\n**Approach:** Mobile-first using Tailwind responsive prefixes (\`sm:\`, \`md:\`, \`lg:\`, \`xl:\`, \`2xl:\`).\n`;
    // Execute statement: content += 'Always design for mobile first, then layer on responsive overrides.\n';
    content += 'Always design for mobile first, then layer on responsive overrides.\n';
  // Execute statement: } else {
  } else {
    // Execute statement: content += '\n**Approach:** Use `@media (min-width: ...)` queries matching the breakpoints above.\n';
    content += '\n**Approach:** Use `@media (min-width: ...)` queries matching the breakpoints above.\n';
  }

  return `## 9. Responsive Behavior

${content}`;
}

// ── Section 10: Agent Prompt Guide ────────────────────────────────────

function generateAgentPromptGuide(profile: DesignProfile): string {
  const bg = profile.colors.find(c => c.role === 'background');
  const surface = profile.colors.find(c => c.role === 'surface');
  const accent = profile.colors.find(c => c.role === 'accent');
  const text = profile.colors.find(c => c.role === 'text-primary');
  const textMuted = profile.colors.find(c => c.role === 'text-muted');
  const border = profile.colors.find(c => c.role === 'border');
  const fonts = [...new Set(profile.typography.map(t => t.fontFamily))].filter(f => f);
  const primaryFont = fonts[0] || 'sans-serif';
  const borderRadius = findBorderRadius(profile);

  const shadowNote = profile.designTraits.hasShadows
    ? 'Use shadow tokens from Section 6.'
    : 'No shadows — use borders and surface colors for depth.';

  let content = 'Use these as starting points when building new UI:\n\n';

  // Helper: use extracted token or a CSS variable reference, never a hardcoded hex
  const col = (token: any, varName: string): string => token?.hex || `var(--${varName})`;

  // Card prompt
  content += '### Build a Card\n\n';
  // Execute statement: content += '```\n';
  content += '```\n';
  content += `Background: ${col(surface || bg, 'surface')}\n`;
  content += `Border: 1px solid ${col(border, 'border')}\n`;
  content += `Radius: ${borderRadius}\n`;
  content += `Padding: ${pickSpacing(profile.spacing, 4)}px\n`;
  content += `Font: ${primaryFont}\n`;
  content += `${shadowNote}\n`;
  // Execute statement: content += '```\n\n';
  content += '```\n\n';

  // Button prompt
  content += '### Build a Button\n\n';
  // Execute statement: content += '```\n';
  content += '```\n';
  content += `Primary: bg ${col(accent, 'accent')}, text white\n`;
  content += `Ghost: bg transparent, border ${col(border, 'border')}\n`;
  content += `Padding: ${pickSpacing(profile.spacing, 2)}px ${pickSpacing(profile.spacing, 4)}px\n`;
  content += `Radius: ${borderRadius}\n`;
  content += `Hover: opacity 0.9 or lighter shade\n`;
  content += `Focus: ring with ${col(accent, 'accent')}\n`;
  // Execute statement: content += '```\n\n';
  content += '```\n\n';

  // Page layout prompt
  content += '### Build a Page Layout\n\n';
  // Execute statement: content += '```\n';
  content += '```\n';
  content += `Background: ${col(bg, 'background')}\n`;
  content += `Max-width: ${profile.containerMaxWidth || '1280px'}, centered\n`;
  content += `Grid: ${profile.spacing.base}px base\n`;
  content += `Responsive: mobile-first, breakpoints from Section 9\n`;
  // Execute statement: content += '```\n\n';
  content += '```\n\n';

  // Stats / Data card
  content += '### Build a Stats Card\n\n';
  // Execute statement: content += '```\n';
  content += '```\n';
  content += `Surface: ${col(surface || bg, 'surface')}\n`;
  content += `Label: ${col(textMuted, 'text-muted')} (muted, 12px, uppercase)\n`;
  content += `Value: ${col(text, 'text-primary')} (primary, 24-32px, bold)\n`;
  content += `Status: use success/warning/danger from Section 2\n`;
  // Execute statement: content += '```\n\n';
  content += '```\n\n';

  // Form
  content += '### Build a Form\n\n';
  // Execute statement: content += '```\n';
  content += '```\n';
  content += `Input bg: ${col(bg, 'background')}\n`;
  content += `Input border: 1px solid ${col(border, 'border')}\n`;
  content += `Focus: border-color ${col(accent, 'accent')}\n`;
  content += `Label: ${col(textMuted, 'text-muted')} 12px\n`;
  content += `Spacing: ${pickSpacing(profile.spacing, 4)}px between fields\n`;
  content += `Radius: ${borderRadius}\n`;
  // Execute statement: content += '```\n\n';
  content += '```\n\n';

  // General
  content += '### General Component\n\n';
  // Execute statement: content += '```\n';
  content += '```\n';
  content += `1. Read DESIGN.md Sections 2-6 for tokens\n`;
  content += `2. Colors: only from palette\n`;
  content += `3. Font: ${primaryFont}, type scale from Section 3\n`;
  content += `4. Spacing: ${profile.spacing.base}px grid\n`;
  content += `5. Components: match patterns from Section 4\n`;
  content += `6. Elevation: ${profile.designTraits.hasShadows ? 'shadow tokens' : 'flat, surface shifts'}\n`;
  // Execute statement: content += '```\n';
  content += '```\n';

  // Return value `## 10. Agent Prompt Guide to caller
  return `## 10. Agent Prompt Guide

${content}`;
}

// Define function findBorderRadius(profile: DesignProfile)
function findBorderRadius(profile: DesignProfile): string {
  // Define constant radii set to profile.borderRadius.filter(r => !r.includes('9999'));
  const radii = profile.borderRadius.filter(r => !r.includes('9999'));
  // Check condition: radii.length > 0
  if (radii.length > 0) {
    // Return value radii[Math.floor(radii.length / 2)]; to caller
    return radii[Math.floor(radii.length / 2)];
  }
  // Define constant radiusVar set to profile.cssVariables.find(v => /radius/i.test(v.name));
  const radiusVar = profile.cssVariables.find(v => /radius/i.test(v.name));
  // Check condition: radiusVar
  if (radiusVar) return radiusVar.value;
  // Return value '8px'; to caller
  return '8px';
}

// ── Helpers ───────────────────────────────────────────────────────────

// Define function pickSpacing(spacing: { base: number; values: number[] }, multiplier: number)
function pickSpacing(spacing: { base: number; values: number[] }, multiplier: number): number {
  // Define constant target set to spacing.base * multiplier;
  const target = spacing.base * multiplier;
  // Define constant clamped set to Math.min(target, 32);
  const clamped = Math.min(target, 32);
  // Check condition: spacing.values.length > 0
  if (spacing.values.length > 0) {
    // Define constant closest set to spacing.values.reduce((prev, curr) =>
    const closest = spacing.values.reduce((prev, curr) =>
      // Execute statement: Math.abs(curr - clamped) < Math.abs(prev - clamped) ? curr : prev
      Math.abs(curr - clamped) < Math.abs(prev - clamped) ? curr : prev
    );
    // Return value closest; to caller
    return closest;
  }
  // Return value clamped; to caller
  return clamped;
}
