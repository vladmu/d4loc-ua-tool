"""Which application is running: the full Toolkit (installer and translator tool) or the players' Installer (the same code without the translator tool).

The players' executable starts through d4loc/installer.py, which switches the translator tool off before the window is built.
"""
TRANSLATOR = True
NAME_TOOLKIT = "D4 UA Localization Toolkit"
NAME_INSTALLER = "D4 UA Localization Installer"


def app_name():
    return NAME_TOOLKIT if TRANSLATOR else NAME_INSTALLER
