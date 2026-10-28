"""PySide6 desktop shell: floating HUD, Command Center, approvals, tray.

The UI never calls models or tools directly. It sends requests to the
engine on a worker thread and receives engine events through ``UiBridge``,
which re-emits them as Qt signals on the GUI thread.
"""
