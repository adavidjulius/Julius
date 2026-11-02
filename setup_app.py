"""
py2app setup script for Julius Agent macOS .app bundle.

Usage:
    .venv/bin/python3 setup_app.py py2app

This will create dist/Julius Agent.app
"""

from setuptools import setup
import py2app.recipes

class ExcludeFromZip_Recipe(object):
    def __init__(self, module):
        self.module = module
    def check(self, cmd, mf):
        m = mf.findNode(self.module)
        if m is None:
            return None
        return {"packages": [self.module]}

# Force playwright to be copied as a loose directory on the filesystem
setattr(py2app.recipes, 'playwright', ExcludeFromZip_Recipe('playwright'))

APP = ['julius_gui.py']
APP_NAME = 'Julius Agent'

DATA_FILES = ['frontend', 'assets', 'custom_voice_models', '.env']

OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'assets/icon.icns',
    'plist': {
        'CFBundleName': APP_NAME,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleIdentifier': 'com.juliusagent.desktop',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSMinimumSystemVersion': '11.0',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,  # Support dark mode
    },
    'includes': [
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'src',
        'src.web_agent',
        'src.agent_config',
        'src.agent_prompts',
        'src.llm_web_client',
        'src.action_executor',
        'src.shell_manager',
        'src.ledger',
        'src.security_policy',
        'src.rag_engine',
        'src.chat_providers',
        'src.chat_providers.deepseek',
        'src.chat_providers.chatgpt',
        'src.chat_providers.grok',
        'src.chat_providers.perplexity',
        'src.chat_providers.base',
        'rich',
        'pynput',
        'qasync',
        'keyring',
        'cryptography',
    ],
    'excludes': [
        'rubicon',
        'rubicon.objc',
        'rubicon-objc',
        'tkinter',
        'matplotlib',
        'scipy',
        'PIL',
        'cv2',
        'test',
        'unittest',
        'playwright._impl.__pyinstaller',
        'playwright',
    ],
    'packages': ['src', 'src.chat_providers', 'PyQt6', 'keyring', 'cryptography', 'playwright'],
}

setup(
    name=APP_NAME,
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
