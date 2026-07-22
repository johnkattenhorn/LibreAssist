# -*- coding: utf-8 -*-
# libreassist/backup.py - Backup and restore functions

import os
import shutil
import time
import uno
from .document import getCurrentDocument, getDocumentPath
from .settings import getDocSettingsDir, loadSettings, saveSettings

_undo_state = "original"  # Track state: "original" or "changed"


def createBackup(fullPath, docDir):
    """
    Create a backup of the document before the provider modifies it.
    Safe to call from the Main-UNO-Thread – does not use getCurrentDocument().

    Args:
        fullPath: Absolute path to the document file
        docDir:   Settings directory for this document

    Returns: True if successful, False otherwise
    """
    try:
        if not fullPath or not docDir:
            return False
        filename = os.path.basename(fullPath)
        backupPath = os.path.join(docDir, "backup" + os.path.splitext(filename)[1])
        shutil.copy2(fullPath, backupPath)
        return True
    except Exception as e:
        print(f"Error creating backup: {e}")
        return False


def restoreBackup():
    """
    Restore document from backup (Undo).
    Called from the Undo button - getCurrentDocument() is correct here.
    Handles both edited source documents and newly created documents.
    Returns: Status message string
    """
    global _undo_state

    try:
        directory, filename, fullPath = getDocumentPath()
        if not fullPath:
            return "Document not saved"

        docDir = getDocSettingsDir()
        data   = loadSettings()

        # Newly created document: delete it instead of restoring the source
        if data.get("last_action") == "create":
            return _undoCreate(data, docDir)

        # Edited source document: restore from backup (original behaviour)
        doc = getCurrentDocument()
        if not doc:
            return "No document open"

        backupPath = os.path.join(docDir, "backup" + os.path.splitext(filename)[1])
        if not os.path.exists(backupPath):
            return "No backup available"

        frame = doc.getCurrentController().getFrame()
        frameName = frame.getName()
        if not frameName:
            frameName = f"la_{id(frame)}"
            frame.setName(frameName)
        url = doc.getURL()

        data["undo_available"] = False
        data["redo_available"] = True
        saveSettings(data)

        doc.close(False)
        time.sleep(0.3)

        shutil.copy2(backupPath, fullPath)

        ctx = uno.getComponentContext()
        desktop = ctx.ServiceManager.createInstance("com.sun.star.frame.Desktop")
        desktop.loadComponentFromURL(url, frameName, 0, ())

        _undo_state = "original"
        return "Document restored from backup"

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error restoring backup: {str(e)}"


def restoreChanged():
    """
    Restore document from changed state (Redo).
    Called from the Redo button - getCurrentDocument() is correct here.
    Handles both edited source documents and newly created documents.
    Returns: Status message string
    """
    global _undo_state

    try:
        directory, filename, fullPath = getDocumentPath()
        if not fullPath:
            return "Document not saved"

        docDir = getDocSettingsDir()
        data   = loadSettings()

        # Newly created document: re-create it from the stored copy
        if data.get("last_action") == "create":
            return _redoCreate(data, docDir)

        doc = getCurrentDocument()
        if not doc:
            return "No document open"

        changedPath = os.path.join(docDir, "changed" + os.path.splitext(filename)[1])
        if not os.path.exists(changedPath):
            return "No changed state available"

        frame = doc.getCurrentController().getFrame()
        frameName = frame.getName()
        if not frameName:
            frameName = f"la_{id(frame)}"
            frame.setName(frameName)
        url = doc.getURL()

        data["undo_available"] = True
        data["redo_available"] = False
        saveSettings(data)

        doc.close(False)
        time.sleep(0.3)

        shutil.copy2(changedPath, fullPath)

        ctx = uno.getComponentContext()
        desktop = ctx.ServiceManager.createInstance("com.sun.star.frame.Desktop")
        desktop.loadComponentFromURL(url, frameName, 0, ())

        _undo_state = "changed"
        return "Changes restored"

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error restoring changes: {str(e)}"


def _undoCreate(data, docDir):
    """
    Undo a document-creation action: close and delete the created files.
    The redo copies in docDir are kept so the action can be redone.
    """
    global _undo_state

    _closeAndDeleteFiles(data.get("created_files", []))

    data["undo_available"] = False
    data["redo_available"] = True
    saveSettings(data)

    _undo_state = "original"
    return "Created document removed"


def _redoCreate(data, docDir):
    """
    Redo a document-creation action: restore the created files from the
    stored copies in docDir and re-open them in new windows.
    """
    global _undo_state

    ctx = uno.getComponentContext()
    desktop = ctx.ServiceManager.createInstance("com.sun.star.frame.Desktop")

    for path in data.get("created_files", []):
        copyPath = os.path.join(docDir, "created_" + os.path.basename(path))
        if os.path.exists(copyPath):
            shutil.copy2(copyPath, path)
            desktop.loadComponentFromURL(uno.systemPathToFileUrl(path), "_blank", 0, ())

    data["undo_available"] = True
    data["redo_available"] = False
    saveSettings(data)

    _undo_state = "changed"
    return "Created document restored"


def _closeAndDeleteFiles(paths):
    """
    Close any open window showing one of the given files, then delete the file.
    """
    ctx = uno.getComponentContext()
    desktop = ctx.ServiceManager.createInstance("com.sun.star.frame.Desktop")

    urls = set()
    for path in paths:
        try:
            urls.add(uno.systemPathToFileUrl(path))
        except Exception:
            pass

    # Close matching windows first
    components = desktop.getComponents().createEnumeration()
    while components.hasMoreElements():
        comp = components.nextElement()
        try:
            if comp.getURL() in urls:
                comp.close(False)
        except Exception:
            pass

    time.sleep(0.3)

    # Delete the files
    for path in paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"Error deleting created file {path}: {e}")
