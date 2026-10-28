"""Guide 1: installing N.E.K.O. on a new computer (written for someone who has never used AI)."""

from design import card, document, icon, network, note, orb, page, phone, say, step, table, window

FOOT = "N.E.K.O. - Installation guide"
# (Python 3.11: no backslashes inside {...} of f-strings, so anything with a Windows path lives here)
CMD_BUILD = '<div class="cmdbox">powershell -ExecutionPolicy Bypass -File D:\\PROJECT\\N.E.K.O\\scripts\\build-dist.ps1</div>'
ZIP = "<code>D:\\NEKO-Data\\dist\\NEKO-Setup.zip</code>"
CMD_GPU = '<div class="cmdbox">powershell -ExecutionPolicy Bypass -File D:\\NEKO\\app\\scripts\\share-gpu.ps1</div>'
LIGHT = "<code>.\\install.ps1 -Models light</code>"


def render() -> str:
    p = []
    n = 0

    def add(inner: str, cls: str = "") -> None:
        nonlocal n
        n += 1
        p.append(page(inner, FOOT, n, cls))

    # 1 cover -------------------------------------------------------------------------------------------
    add(f"""
<div class="brand">N . E . K . O .</div>
<div style="text-align:center;margin-top:18mm">{orb(95)}</div>
<h1>Installing your<br>personal AI helper</h1>
<div class="sub">A step-by-step guide to put N.E.K.O. on a new computer.<br>No experience with AI or computers needed.</div>
<div style="margin-top:6mm"><span class="badge">About 30 minutes of your time</span><span class="badge">1-3 hours of waiting</span>
<span class="badge">One double-click</span></div>
<div class="tagline">Neuro Electric Knowledge Operator &middot; runs on your own computer &middot; your data stays with you</div>
""", "cover")

    # 2 what is it + what you need -------------------------------------------------------------------------
    add(f"""
<div class="kicker">Before you start</div>
<h1>What are we installing?</h1>
<p class="lead"><b>N.E.K.O.</b> ("Neko") is a helper that lives on your computer. You talk to her like a person - out loud
or by typing - and she answers, and she can do things on the computer for you: open programs, play music, read files,
set reminders and much more.</p>
<div class="grid3">
{card("mic", "She listens", "Say her name, then what you want. No buttons needed.")}
{card("brain", "She thinks", "An <b>AI</b> (a program that understands language) works out what you mean.")}
{card("shield", "She asks first", "Anything risky waits for your OK. Nothing leaves the PC without permission.")}
</div>
<h2>What you need</h2>
{table(["", "Thing", "Why"], [
        [icon("desktop", size="7mm"), "<b>A Windows 10 or 11 computer</b>", "The computer Neko will live on."],
        [icon("gear", size="7mm"), "<b>An NVIDIA graphics card</b> (6 GB or more is best)",
         "The AI runs on it. The office PC's RTX 5060 Ti 16 GB is perfect. Without one she still works, slower."],
        [icon("download", size="7mm"), "<b>About 60 GB of free disk space</b>", "Most of it is the AI's &quot;brain&quot; files."],
        [icon("cloud", size="7mm"), "<b>Internet during the install</b>", "To download the AI. Afterwards she also works offline."],
        [icon("phone", size="7mm"), "<b>A phone with Telegram</b> (optional)", "To chat with her and approve things from anywhere."],
        [icon("link", size="7mm"), "<b>Tailscale</b> (optional, free)", "A private connection between your computers and phones."],
    ], ["10%", "40%", "50%"])}
{note("info", "Words you will see:", "<b>AI model</b> = the brain file Neko thinks with. <b>Telegram bot</b> = a chat "
      "contact on your phone that is really Neko. <b>Pairing</b> = telling Neko which phone is yours.")}
""")

    # 3 big picture -------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">The big picture</div>
<h1>How everything fits together</h1>
<p class="lead">You can have Neko on more than one computer. Each one is its own Neko with its own memory - but they can
help each other.</p>
{network()}
<div class="grid">
{card("laptop", "The laptop (main PC)", "The owner's computer. It can borrow the office PC's stronger AI when that PC is on, "
      "and it can ask the office Neko to do things there.")}
{card("desktop", "The office PC", "Gets its own Neko with its own name and memory. Its strong graphics card runs bigger, "
      "smarter AI models.", "#b4570d")}
{card("phone", "The owner's phone", "Approves risky actions on <b>both</b> computers, can upgrade Neko. Needs a PIN for "
      "the riskiest things.", "#7c4dff")}
{card("users", "Everyday phones", "For people who use a PC every day: chat, music, reminders, running programs. Anything "
      "risky they ask for goes to the owner's phone.", "#7c4dff")}
</div>
""")

    # 4 part A on the laptop -----------------------------------------------------------------------------
    add(f"""
<div class="kicker">Part A &middot; on the main laptop</div>
<h1>Get the installer ready</h1>
<p class="lead">Do this once on the laptop that already has Neko. It prepares a small package to carry to the new PC.</p>
{step("A1", "Send the newest version to your private online copy",
      "<p>Tell Neko:</p>" + say("Neko, publish the update") +
      "<p>She checks everything, asks you to confirm (on the phone it needs your PIN), and sends the newest Neko to your "
      "private GitHub storage. New computers download their updates from there.</p>")}
{step("A2", "Make the installer package",
      "<p>Open <b>PowerShell</b> (press the Windows key, type <i>PowerShell</i>, press Enter) and paste this line:</p>"
      + CMD_BUILD +
      "<p>After a few seconds you have the file " + ZIP + " (less than 1 MB). It contains "
      "Neko's program only - <b>no memories, no passwords, no keys</b>. The builder refuses to make the package if it "
      "finds anything personal.</p>")}
{step("A3", "Copy it to the new computer",
      "<p>Use a USB stick, Google Drive, OneDrive or any way you like.</p>")}
{note("tip", "Tip:", "You can make a new package any time - it always contains the newest version.")}
""")

    # 5 part B install -----------------------------------------------------------------------------------
    term = """<div class="term">  <span class="c">N.E.K.O. installer</span>

[1] Checking this PC
Windows            Microsoft Windows 11 Pro (build 26100)          <span class="g">ok</span>
CPU                AMD Ryzen 7 7800X3D                             <span class="g">ok</span>
Memory             32 GB                                           <span class="g">ok</span>
Graphics           NVIDIA GeForce RTX 5060 Ti, 16 GB               <span class="g">ok - GPU AI</span>
Free disk (D:)     412 GB                                          <span class="g">ok</span>
Internet           reachable                                       <span class="g">ok</span>

Plan: profile desktop-16gb, speech 'large-v3-turbo' on cuda, models: qwen3:14b, ...
<span class="y">Install N.E.K.O. into D:\\NEKO now? (downloads roughly 35 GB) [Y/n]</span> _</div>"""
    add(f"""
<div class="kicker">Part B &middot; on the new computer</div>
<h1>Install with one double-click</h1>
{step("B1", "Unzip the package", "<p>Right-click <code>NEKO-Setup.zip</code> &rarr; <b>Extract All</b> &rarr; <b>Extract</b>. "
      "A folder <b>NEKO-Setup</b> appears.</p>", "b")}
{step("B2", "Double-click INSTALL.cmd", "<p>A black window opens and checks the computer. It shows what is there and what "
      "is missing:</p>" + window("N.E.K.O. installer", term), "b")}
{step("B3", "Press Enter to say yes - then wait",
      "<p>It now installs Python, Neko, her voice, her hearing, and the AI models sized for this graphics card. "
      "On a normal home connection this takes <b>1-3 hours</b>. You can leave the computer alone - it continues by itself. "
      "If it stops (for example the internet drops), just double-click INSTALL.cmd again: it continues where it stopped.</p>", "b")}
{note("safe", "Old graphics driver?", "RTX 50-series cards need NVIDIA driver 572 or newer. If yours is older, the installer "
      "offers to open NVIDIA's download page. Install the driver, restart, and run INSTALL.cmd again.")}
""")

    # 6 questions + telegram bot ---------------------------------------------------------------------------
    qa = """<div class="term">[8] Your profile
  Your name (what should the assistant call you?): <span class="c">Rafi</span>
  The assistant's name [Neko]: <span class="c">Nova</span>
  Voice: female or male? [female]: <span class="c">female</span>
  Do you also talk to Nova in Bangla? [y/N]: <span class="c">y</span>
  Control Nova from a phone through Telegram? [y/N]: <span class="c">y</span>
    Paste the bot key (or press Enter to skip): <span class="c">************</span>
    <span class="g">bot @office_nova_bot is ready</span>
  Add free cloud brains now? [y/N]: <span class="c">n</span>
Start Nova automatically with Windows? [Y/n]: <span class="c">y</span></div>"""
    add(f"""
<div class="kicker">Part B &middot; a few questions</div>
<h1>Tell her who she is</h1>
<p>Near the end the installer asks some simple questions. Answer for the person who will use <b>this</b> computer:</p>
{window("N.E.K.O. installer - profile", qa)}
<div class="row" style="align-items:flex-start">
<div class="col">
<h2>Making the Telegram bot</h2>
<p>When it asks about Telegram, take <b>your own phone</b> (the owner's):</p>
{step("1", "Open @BotFather", "<p>In Telegram, search <b>@BotFather</b> - pick the one with the <b>blue tick</b>. Tap <b>Start</b>.</p>", "c")}
{step("2", "Send /newbot", "<p>Give it a name (e.g. <i>Office Nova</i>) and a username that ends in <b>bot</b>.</p>", "c")}
{step("3", "Copy the key", "<p>BotFather replies with a long key. Copy it and paste it into the installer.</p>", "c")}
{note("stop", "Always a NEW bot.", "Never use the laptop's bot - two computers on one bot would steal each other's messages "
      "(Neko notices and warns you).")}
</div>
<div style="flex:0 0 66mm">{phone("BotFather", "bot", [("me", "/newbot"), ("bot", "Alright, a new bot. How are we going to call it?"),
        ("me", "Office Nova"), ("bot", "Good. Now let's choose a username for your bot. It must end in 'bot'."),
        ("me", "office_nova_bot"), ("bot", "Done! Use this token to access the HTTP API:<br><b>7xxxxxx:AAF...</b> (keep it secret)")])}</div>
</div>
""")

    # 7 first start + pairing -------------------------------------------------------------------------------
    add(f"""
<div class="kicker">Part B &middot; first start</div>
<h1>Meet her and pair the phones</h1>
<div class="row" style="align-items:flex-start">
<div class="col">
{step("B4", "She starts by herself", "<p>At the end the installer runs a self-test and asks <i>Start now?</i> - say yes. "
      "A glowing orb appears. From now on she starts with Windows, hidden, and appears when you say her name.</p>", "b")}
{step("B5", "Pair the OWNER phone first", "<p>The orb shows a message like <b>Pair your phone: send /pair 482913 to "
      "@office_nova_bot</b>. On <b>your</b> phone, open that bot and send exactly that. She answers <i>Paired as the owner!</i></p>", "b")}
{step("B6", "Set the approval PIN", "<p>Double-click the orb &rarr; <b>Command Center</b> &rarr; <b>Phone</b> &rarr; "
      "<b>3. Approval PIN</b>: type 4-8 digits &rarr; <b>Set PIN</b>. Use a number that isn't your phone's unlock code.</p>", "b")}
{step("B7", "Add the everyday phone", "<p>Same page: <b>Pair an everyday phone</b>. A new code appears; the person who uses "
      "this PC sends <b>/pair</b> and that code from their Telegram to the same bot. Their risky requests will come to "
      "your phone.</p>", "b")}
{step("B8", "Only you approve", "<p>Still on the Phone page, under <b>Approvals</b> tick <b>Only my (owner) phone can "
      "approve</b> and click <b>Save options</b>. Now the approval window on this PC can only say <i>Deny</i> - risky things "
      "need <b>your</b> phone.</p>", "b")}
</div>
<div style="flex:0 0 66mm">
<div style="background:#070b14;border-radius:10px;padding:3mm;text-align:center;color:#cfe3f5;font-size:8.5pt">{orb(40)}
<div>Pair your phone: in Telegram open @office_nova_bot and send <b>/pair 482913</b> (valid 10 minutes)</div></div>
{phone("Office Nova", "bot", [("me", "/pair 482913"), ("bot", "Paired as the owner! Only paired phones are answered, and risky things are approved here."),
        ("me", "hi"), ("bot", "Hi! I'm Nova on your phone. What can I do for you?")])}
</div></div>
""")

    # 8 tailscale, link, calls ----------------------------------------------------------------------------
    add(f"""
<div class="kicker">Part C &middot; optional extras</div>
<h1>Connect the computers and phones</h1>
<p class="lead">These are optional, but they make Neko much more useful. All of them use <b>Tailscale</b> - a free app that
makes a private, encrypted network just for your own devices.</p>
{step("C1", "Install Tailscale everywhere", "<p>Get Tailscale from <b>tailscale.com/download</b> on the laptop, the office PC and "
      "your phones. Sign in with the <b>same account</b> on all of them.</p>", "c")}
{step("C2", "Let the laptop use the office PC's AI power", "<p>On the office PC, in PowerShell:</p>"
      + CMD_GPU +
      "<p>Now, whenever the office PC is on, the laptop automatically thinks with the office PC's bigger AI.</p>", "c")}
{step("C3", "Link the two Nekos", "<p>On the office PC: Command Center &rarr; Phone &rarr; <b>Let my other PC connect</b> "
      "and copy the code. On the laptop: Command Center &rarr; Phone &rarr; <b>Connect to my other PC</b> and paste it. Then "
      "the laptop can answer:</p>" + say("what can the office PC do that you can't?", "on the office PC, run Print SOFT"), "c")}
{step("C4", "Phone calls", "<p>Command Center &rarr; Phone &rarr; <b>Turn on calls</b> &rarr; <b>Send call link to my phone</b>. "
      "Tap the link on the phone and talk to her like a phone call (earbuds and smart glasses work too).</p>", "c")}
{note("safe", "Safe by design:", "nothing here opens the computer to the internet. Only devices signed in to <b>your</b> "
      "Tailscale account can reach it, and each connection also needs its own secret key.")}
""")

    # 9 updates, troubleshooting, uninstall ---------------------------------------------------------------
    add(f"""
<div class="kicker">Afterwards</div>
<h1>Updates and if something goes wrong</h1>
<h2>Updates (one click)</h2>
<p>When a new version is published, the office Neko says <i>An update for me is ready</i>. Click the small Neko icon near the
clock &rarr; <b>Install update</b>. She makes a backup, updates, tests herself, and <b>goes back automatically</b> if anything
fails. Her memory, phones and keys are never touched.</p>
<h2>Troubleshooting</h2>
{table(["What you see", "What to do"], [
        ["The installer stopped with a red message", "Read the message, fix it (often: no internet), then double-click "
         "<b>INSTALL.cmd</b> again. It continues where it stopped."],
        ["'Your NVIDIA driver is too old'", "Install the newest driver from nvidia.com, restart, run the installer again."],
        ["Not enough disk space", "Free some space, or run it with smaller models: in PowerShell "
         + LIGHT + " (about 18 GB)."],
        ["The orb doesn't appear", "Double-click the <b>Nova/Neko</b> icon on the Desktop. Or restart the PC."],
        ["She doesn't hear me", "Check the microphone in Windows sound settings; speak after saying her name clearly."],
        ["'bot key used by another PC'", "Make a NEW bot for this PC in @BotFather and paste its key in "
         "Command Center &rarr; Phone &rarr; 1."],
        ["Phone pairing code expired", "Command Center &rarr; Phone &rarr; <b>Pair my phone</b> for a fresh code."],
        ["Call page says 'Can't reach Neko'", "The PC is off/asleep, or Tailscale isn't connected on the phone."],
    ], ["40%", "60%"])}
<h2>Removing Neko</h2>
<p>Delete the folder <code>D:\\NEKO</code>, the folder <code>%LOCALAPPDATA%\\NEKO</code> (her memory) and the Desktop
shortcut. In @BotFather you can send <code>/deletebot</code> to remove the phone bot too.</p>
""")
    return document("Installing N.E.K.O.", p)
