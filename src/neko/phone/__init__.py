"""Talk to N.E.K.O. from your phone.

* ``telegram.py`` - chat through your own Telegram bot (text, voice notes, photos, files). Outgoing
  connections only; only your paired chat is ever answered.
* ``service.py``  - pairing, the approval PIN, phone approvals, alerts (reminders, finished jobs, battery).
* ``call.py``     - the live call page, served on 127.0.0.1 and shared only inside your Tailscale network.

Everything from the phone runs through the same engine and permission policy as on the PC
(core/origin.py marks it, so the PC's orb stays quiet).
"""
