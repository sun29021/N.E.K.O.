"""Guide 2: the owner's manual for the main laptop."""

from design import (card, document, how_it_works, icon, network, note, orb, orb_states, page, phone, say, step,
                    table, traffic_light, window)

FOOT = "N.E.K.O. - Owner's manual (laptop)"
PROJ = "D:\\PROJECT"          # (no backslashes inside f-string expressions on Python 3.11)
NOTES = "D:\\NEKO-Notes\\Study"
HANDBOOK = "learn this D:\\Docs\\company handbook.pdf"
ARCHIVE = "Move 14 files to D:\\Archive"


def approval_window() -> str:
    inner = """<div class="dialog"><b style="color:#9a5b00">Material change</b> &nbsp; level 2 &middot; tool <code>run_program</code>
<div style="margin:2mm 0;font-size:10.5pt">Run your program Traid by SUN with --report daily</div>
<div class="small">Effect: runs your program. Can be undone: NO.</div>
<div class="small" style="margin-top:1.5mm">Only approve if you asked for this.</div>
<div class="btnrow"><span class="btn def">Deny</span><span class="btn">Approve</span></div></div>"""
    return window("N.E.K.O. needs your approval", inner)


def render() -> str:
    p: list[str] = []
    n = 0

    def add(inner: str, cls: str = "") -> None:
        nonlocal n
        n += 1
        p.append(page(inner, FOOT, n, cls))

    # 1 cover ---------------------------------------------------------------------------------------------
    add(f"""
<div class="brand">N . E . K . O .</div>
<div style="text-align:center;margin-top:16mm">{orb(95, "#a06bff")}</div>
<h1>Your AI helper:<br>the owner's manual</h1>
<div class="sub">Everything Neko can do on your main laptop - what to say, what happens, and how you stay in control.</div>
<div style="margin-top:6mm"><span class="badge">Talk or type</span><span class="badge">Control your PC</span>
<span class="badge">From your phone</span><span class="badge">Two computers</span></div>
<div class="tagline">For the owner's laptop &middot; the office PC has its own, simpler guide</div>
""", "cover")

    # 2 contents + meet neko --------------------------------------------------------------------------------
    toc = [("1", "Meet Neko"), ("2", "Waking her up and talking"), ("3", "Staying in control"), ("4", "Everyday help"),
           ("5", "Controlling your PC"), ("6", "Music"), ("7", "Files, PDFs and studying"),
           ("8", "Reminders, skills, teaching her"), ("9", "Your own programs"), ("10", "Neko on your phone"),
           ("11", "Your two computers"), ("12", "Upgrading Neko"), ("13", "The Command Center"),
           ("14", "Cheat sheet"), ("15", "Questions and problems")]
    add(f"""
<div class="kicker">Contents</div>
<div class="toc">{"".join(f"<div><b>{a}</b>{b}</div>" for a, b in toc)}</div>
<h1 style="margin-top:8mm">1 &middot; Meet Neko</h1>
<p class="lead">Neko is a helper that lives on this laptop. Think of her as a smart assistant sitting next to you: you
<b>say</b> or <b>type</b> what you want in normal words, and she answers - or does it for you on the computer.</p>
{how_it_works()}
<h2>Where does she think?</h2>
<p>The "thinking" is done by an <b>AI model</b> - a program trained on huge amounts of text, so it understands everyday
language. Neko picks the best brain for each job by herself:</p>
<div class="grid3">
{card("laptop", "On this laptop", "Private and free. Works without internet. A smaller brain, because this laptop's graphics card is small.")}
{card("desktop", "On the office PC", "When the office PC is on, she borrows its much bigger brain automatically. Still private.", "#b4570d")}
{card("cloud", "Free cloud brains", "Very fast and smart (Groq, Gemini). Used for normal chats when internet is on; private things stay local.", "#3a5bd9")}
</div>
{note("info", "Her memory is hers:", "what she learns about you is stored on this laptop only (in your user folder), never in "
      "the program files, and the office PC has a separate memory.")}
""")

    # 3 waking + talking -------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">2 &middot; Waking her up and talking</div>
<h1>Just say her name</h1>
<p class="lead">Neko starts with Windows and waits quietly in the background. The glowing <b>orb</b> shows what she's doing:</p>
{orb_states()}
<div class="grid" style="margin-top:5mm">
{card("mic", "Talk", "Say <b>Neko</b>, then your request in one go: " + say("Neko, what's the weather in Dhaka?") +
      "<br>After she answers you have <b>15 seconds</b> to keep talking without her name.")}
{card("chat", "Type", "Click the orb's text box (or double-click the orb for the big <b>Command Center</b>) and type. "
      "Typing always works perfectly - even when it's noisy.")}
{card("speaker", "Interrupt her", say("Neko, stop") + " silences her. " + say("Neko, wait - play Believer") +
      " changes your request while she's talking.")}
{card("eye", "Subtitles", "While she speaks, her words appear on screen one by one - easy to follow.")}
</div>
<h2>Good to know</h2>
<ul>
<li>After 4 quiet minutes the orb fades away - she is still listening. Say <b>Neko</b> and she comes back.</li>
<li>She mishears a name? Say {say("Neko, learn the word Oporadhi")} - she'll spell it right from then on.</li>
<li>Change her voice: {say("use a male voice")} {say("switch to female voice")} {say("speak Bangla")} {say("speak English")}</li>
<li>To close her: {say("Neko, shut down")} or the small orb icon near the clock &rarr; <b>Quit</b>.</li>
</ul>
""")

    # 4 safety ---------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">3 &middot; Staying in control</div>
<h1>She asks before anything risky</h1>
<p class="lead">Every action has a colour. Neko can never give herself permission - only you can.</p>
{traffic_light()}
<div class="row" style="align-items:flex-start;margin-top:3mm">
<div class="col">
<h3>The approval window</h3>
<p><b>Deny</b> is the default - pressing Enter by accident says no. Red actions also need you to tick
<i>I understand</i>. No answer within about 5 minutes counts as <b>Deny</b>.</p>
<p>When you're away, the same question comes to your phone with <b>Approve</b> / <b>Deny</b> buttons (red ones need your PIN).</p>
</div>
<div style="flex:0 0 88mm">{approval_window()}</div>
</div>
{note("stop", "Emergency stop:", "press <b>Ctrl+Shift+F12</b> (or the red <b>EMERGENCY STOP</b> button in the Command Center). "
      "Everything stops, waiting approvals are denied, and no action runs until you press <b>Resume</b>.")}
{note("safe", "Tricks don't work on her:", "if a document, web page or forwarded message tries to tell her to do something, she treats it "
      "as information only and asks you first. She never types passwords and never clicks in Windows security windows.")}
""")

    # 5 everyday help ------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">4 &middot; Everyday help</div>
<h1>Ask anything</h1>
{table(["Say...", "What happens"], [
        [say("explain photosynthesis simply"), "She answers in plain words (short or detailed - just ask)."],
        [say("think carefully about my business plan"), "Deep mode: she takes longer and thinks step by step."],
        [say("show me how a jet engine works"), "A panel opens next to her with the answer and a picture. "
         + say("show me again") + " brings it back."],
        [say("what's the weather in Dhaka?"), "Today's weather (needs internet)."],
        [say("search Google for best biryani"), "Opens the search in your browser."],
        [say("what's wrong on my screen?"), "She looks at your screen and explains (if a vision model is installed)."],
        [say("how much RAM is free?"), "Checks your computer's health."],
        [say("show me your brain") + say("open your tool armory"), "A 3D map of what she knows / a list of all her abilities."],
    ], ["45%", "55%"])}
<h2>Her memory</h2>
<div class="grid">
{card("book", "She remembers what you tell her", say("remember that my shop opens at 10") + say("remember that I prefer short answers") +
      "<br>Later she uses it by herself.")}
{card("search", "...and long conversations", say("what did I tell you about the bank last week?") +
      "<br>She searches everything you've talked about.")}
</div>
{note("tip", "Change your mind?", say("forget my old address") + " deletes a memory. You can see, edit and delete everything in "
      "Command Center &rarr; <b>Memory</b>.")}
""")

    # 6 control pc ---------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">5 &middot; Controlling your PC</div>
<h1>Your hands-free remote control</h1>
{table(["Say...", "What happens", ""], [
        [say("open Chrome") + say("open YouTube") + say("open my Downloads"), "Opens any app, website, file or folder.", '<span class="chip g">green</span>'],
        [say("open bluetooth settings"), "Opens that Windows Settings page.", '<span class="chip g">green</span>'],
        [say("close Discord") + say("minimise Word") + say("switch to WhatsApp"), "Manages windows.", '<span class="chip g">green</span>'],
        [say("volume up") + say("mute") + say("unmute"), "Sound control.", '<span class="chip g">green</span>'],
        [say('type "hello everyone"'), "Types into the window you're using.", '<span class="chip y">asks</span>'],
        [say("lock my PC"), "Locks the screen.", '<span class="chip g">green</span>'],
        [say("put my PC to sleep"), "Sleep.", '<span class="chip y">asks</span>'],
        [say("restart my PC") + say("shut down my PC"), "30-second countdown; " + say("cancel the shutdown") + " stops it.",
         '<span class="chip r">asks</span>'],
    ], ["46%", "40%", "14%"])}
<h2>Buttons and menus inside apps</h2>
<p>She can press buttons and use menus inside programs, by their names:</p>
<p>{say("in Calculator click Seven")} {say("in Notepad open File > Save as")} {say("what buttons are in this window?")}
{say("turn on dark mode in Settings")}</p>
{note("safe", "Always asks:", "anything that sounds like <b>delete, send, pay, buy, uninstall, sign out</b> or <b>submit</b>. "
      "Typing into a field asks too. She never fills in passwords.")}
""")

    # 7 music + files -----------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">6 &middot; Music &nbsp; 7 &middot; Files and studying</div>
<h1>Music and documents</h1>
<div class="grid">
{card("music", "Music from YouTube", say("play Believer by Imagine Dragons") + say("pause") + say("resume") + say("louder") +
      say("quieter") + say("play next") + say("skip") + say("stop the music") +
      "<p class='small'>She plays the sound only (no video). When a song ends, the next related song starts by itself - like "
      "YouTube. While music plays, short words like <i>pause</i> or <i>skip</i> work without her name. If the PC is muted, "
      "she unmutes it first.</p>")}
{card("file", "Reading files", say("read the hisab manual pdf") + say("summarize this") +
      "<p class='small'>She finds files by name in your folders, or reads the file you clicked in File Explorer. "
      "PDF, Word, PowerPoint and text files.</p>")}
</div>
<h2>Exam tomorrow?</h2>
{step("1", "Ask for study help", say("I have an exam tomorrow - make simpler notes and a cheat sheet from this PDF"))}
{step("2", "She makes two PDFs", f"<p>3-4 pages of easy notes and a one-page cheat sheet, saved in <code>{NOTES}</code>. A panel "
      "shows the cheat sheet with <b>Open PDF</b> buttons.</p>")}
{step("3", "Keep chatting", "<p>Long jobs run in the background - you can keep talking to her meanwhile.</p>")}
{note("tip", "Accuracy:", "always check important facts against your original material.")}
""")

    # 8 reminders, skills, learn this ---------------------------------------------------------------------
    add(f"""
<div class="kicker">8 &middot; Reminders, skills and teaching her</div>
<h1>She learns how you work</h1>
<div class="grid">
{card("bell", "Reminders", say("remind me at 6 to call Ammu") + say("remind me in 20 minutes to check the rice") +
      say("remind me tomorrow at 9 to pay the bill") + say("what are my reminders?") + say("cancel my reminders") +
      "<p class='small'>When it's time she says it on the PC <b>and</b> messages your phone.</p>")}
{card("star", "Learned skills", "Let her do a few steps, for example " + say("open Excel") + say("in Excel click Blank workbook") +
      "then say " + say("save that as monthly sheet") + "Next time just say " + say("do the monthly sheet") +
      "<p class='small'>" + say("what skills do you know?") + say("forget the skill monthly sheet") +
      " - every step still asks when it needs approval.</p>", "#b4570d")}
</div>
<h2>Teach her new knowledge</h2>
<p>Give her text, a file or a web link - she keeps the important facts in her memory and uses them when you ask:</p>
<p>{say("learn this: our shop's Wi-Fi printer is the HP 401 on the 2nd floor")}
{say(HANDBOOK)} {say("learn this https://example.com/price-list")}</p>
<p>From the phone: send the file in Telegram with the caption <b>learn this</b>.
To remove it again: {say("forget what you learned from company handbook")}</p>
{note("safe", "Safety:", "she never takes orders from what she reads, and drops anything that looks like a password or a hidden "
      "instruction. Learned facts are marked as coming from a file - you can see and delete them in Command Center &rarr; Memory.")}
""")

    # 9 programs ----------------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">9 &middot; Your own programs</div>
<h1>She runs the programs you made</h1>
<p class="lead">Neko knows your projects folder <code>{PROJ}</code>. She can run your Python tools, Windows apps, scripts and
web apps - after you approve them once.</p>
{step("1", "See what she found", say("what programs do I have?") + "<p class='small'>She lists your projects and the program "
      "she would start for each (the real app or launcher - never installers).</p>")}
{step("2", "Teach her one", say("learn to use Traid") + "<p class='small'>She reads its description (without running it) and "
      "asks you once. Wrong file? Name it exactly: <i>learn to use</i> and the full path of the file.</p>")}
{step("3", "Use it", say("run Traid") + say("run Traid with --report daily") + say("start HISAB") + say("stop HISAB") +
      "<p class='small'>Tools that print a result: she runs them and tells you what they printed. Apps, servers and web apps "
      "start in the background - web apps open in your browser when ready.</p>")}
{step("4", "Stop the questions (optional)", say("always allow Traid") + "<p class='small'>After you approve it, that one program "
      "runs without asking for 30 days. Others still ask.</p>")}
{note("tip", "Buttons inside your app:", "ask her to click them one by one, then " + say("save that as print the daily bill") +
      " - next time she does all the clicks by herself.")}
""")

    # 10 phone ----------------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">10 &middot; Neko on your phone</div>
<h1>Talk to her from anywhere</h1>
<div class="row" style="align-items:flex-start">
<div class="col">
<p>Your phone is the <b>owner</b> phone (Telegram). Talk to her like on the PC - text or <b>voice notes</b> (she answers with a
voice note).</p>
{table(["Send", "What happens"], [
        ["a photo + <i>what is this?</i>", "She describes it."],
        ["a PDF + <i>summarize this</i>", "Saved on the PC, then summarized."],
        ["a file + <i>learn this</i>", "She learns its facts."],
        [say("lock my PC") + say("play music on the PC"), "Done on the laptop."],
        [say("send me my screen"), "A screenshot comes to your phone (asks first)."],
        ["<b>/status</b>", "Is the PC on? Battery, sound."],
        ["<b>/call</b>", "A private link for a live voice call."],
    ], ["48%", "52%"])}
<p class="small">She also messages you when a reminder is due, when a long job finishes, or when the battery is low.</p>
</div>
<div style="flex:0 0 66mm">{phone("Neko", "bot", [("me", "move the old invoices to the archive folder"),
        ("bot", "Approve this?<br>" + ARCHIVE + "<br>Risk: medium - can be undone: yes")], ("Approve", "Deny"))}
<div class="figcap">Risky things ask on your phone. Red ones also need your PIN - the PIN message is deleted from the chat.</div></div>
</div>
<h2>Live calls</h2>
<p>Send <b>/call</b>, tap the link, tap <b>Call</b> and just talk - she answers sentence by sentence with subtitles, and you can
interrupt her by talking. Bluetooth earbuds and smart glasses work as the headset. (Needs Tailscale on the phone.)</p>
""")

    # 11 two computers --------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">11 &middot; Your two computers</div>
<h1>The laptop and the office PC</h1>
{network()}
<div class="grid">
{card("brain", "Borrowing the big brain", "When the office PC is on, the laptop automatically thinks with its bigger AI. "
      "Nothing to do - it just gets smarter and faster.")}
{card("link", "Using the office PC from here", say("what can the office PC do that you can't?") + say("on the office PC, run Print SOFT") +
      say("ask the office PC to remind me at 5 to close the shop") + "<p class='small'>Risky things are approved on your phone.</p>", "#b4570d")}
{card("star", "Sharing skills", say("get the skill print invoice from the office PC") + say("send the skill monthly sheet to the office PC") +
      "<p class='small'>Memories stay separate on each PC.</p>", "#7c4dff")}
{card("users", "Everyday phones", "Command Center &rarr; Phone &rarr; <b>Pair an everyday phone</b> for someone who uses a PC daily. "
      "Their risky requests come to <b>your</b> phone; they can't upgrade or publish. On the office PC also tick "
      "<b>Only my (owner) phone can approve</b> - then nobody at that screen can approve, only you.", "#7c4dff")}
</div>
""")

    # 12 upgrading ------------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">12 &middot; Upgrading Neko</div>
<h1>She can add new abilities to herself</h1>
<p class="lead">Ask for a new feature in plain words. Claude Code (a coding AI) writes it, and Neko checks it carefully.</p>
{step("1", "Ask", say("upgrade yourself so you can read Excel files") + "<p class='small'>You approve the change first (on the PC or your phone).</p>")}
{step("2", "She tests herself", "<p>She saves a checkpoint, the change is made, then she runs <b>all her tests</b>. If anything "
      "fails she <b>undoes it by herself</b> - she stays exactly as before.</p>")}
{step("3", "Restart", say("restart yourself") + "<p class='small'>From the phone too - she messages you <i>I'm back</i> with her new version.</p>")}
{step("4", "Changed your mind?", say("undo the last upgrade"))}
{step("5", "Send it to the office PC", say("publish the update") + "<p class='small'>Asks every time (PIN on the phone). The office PC "
      "then shows <b>Install update</b>.</p>")}
{note("info", "If your Claude subscription ends:", "everything else keeps working (local + free cloud brains). Only "
      "self-upgrades and big coding jobs stop. Options: pay per use with an Anthropic API key, or add a free coding agent "
      "(Gemini CLI) as a backup.")}
""")

    # 13 command center ---------------------------------------------------------------------------------------------
    cc = """<div class="tabs"><span>Chat</span><span>Activity</span><span>Memory</span><span>Models &amp; Resources</span>
<span>Diagnostics</span><span>Settings</span><span class="on">Phone</span></div>
<div class="dialog" style="font-size:8.8pt;background:#fff">
<div><b>Status</b> &nbsp; Telegram: connected, owner paired &nbsp;|&nbsp; Calls: on</div>
<div style="margin-top:1.5mm"><b>1. Telegram bot key</b> &nbsp; <span class="btn">Make a bot</span> <span class="btn def">Save &amp; connect</span></div>
<div style="margin-top:1.5mm"><b>2. Pairing</b> &nbsp; <span class="btn">Pair my phone</span> <span class="btn">Pair an everyday phone</span></div>
<div style="margin-top:1.5mm"><b>3. Approval PIN</b> &nbsp; <span class="btn">Set PIN</span> &nbsp; <b>4. Live calls</b> <span class="btn">Turn on calls</span></div>
<div style="margin-top:1.5mm"><b>5. My other PC</b> &nbsp; <span class="btn">Let my other PC connect</span> <span class="btn">Connect to my other PC</span></div></div>"""
    add(f"""
<div class="kicker">13 &middot; The Command Center</div>
<h1>Her control room</h1>
<p>Double-click the orb (or right-click it) to open the <b>Command Center</b>:</p>
{window("N.E.K.O. Command Center", cc)}
{table(["Tab", "What it's for"], [
        ["<b>Chat</b>", "A big chat window with the full history."],
        ["<b>Activity</b>", "Everything she did and why - a diary of her actions."],
        ["<b>Memory</b>", "See, approve, edit and delete what she remembers."],
        ["<b>Models &amp; Resources</b>", "Which AI brain she used, memory and graphics card usage."],
        ["<b>Diagnostics</b>", "Health check and <b>Back up now</b> (do it weekly)."],
        ["<b>Settings</b>", "Your name, voice, language, internet on/off, folders she may use, free cloud keys, start with Windows."],
        ["<b>Phone</b>", "Telegram, pairing, PIN, calls and the link to your other PC."],
    ], ["28%", "72%"])}
""")

    # 14-15 cheat sheet ------------------------------------------------------------------------------------------------
    rows = [
        ["Wake / stop", "Neko, ... &middot; Neko, stop &middot; Neko, wait - ... &middot; Neko, shut down"],
        ["Voice", "use a male voice &middot; switch to female voice &middot; speak Bangla &middot; speak English &middot; learn the word ..."],
        ["Questions", "explain ... simply &middot; think carefully about ... &middot; show me ... &middot; show me again &middot; weather in ..."],
        ["Memory", "remember that ... &middot; forget ... &middot; what did I tell you about ...?"],
        ["PC", "open ... &middot; close ... &middot; minimise ... &middot; switch to ... &middot; volume up/down &middot; mute &middot; unmute"],
        ["Power", "lock my PC &middot; put my PC to sleep &middot; restart / shut down my PC &middot; cancel the shutdown"],
        ["Inside apps", "in Calculator click Seven &middot; in Notepad open File > Save as &middot; what buttons are in this window?"],
        ["Music", "play ... &middot; pause &middot; resume &middot; louder &middot; quieter &middot; play next &middot; skip &middot; stop the music"],
        ["Files", "read the ... pdf &middot; summarize this &middot; make notes and a cheat sheet from this PDF"],
        ["Reminders", "remind me at 6 to ... &middot; in 20 minutes ... &middot; what are my reminders? &middot; cancel my reminders"],
        ["Skills", "save that as ... &middot; do the ... &middot; what skills do you know? &middot; forget the skill ..."],
        ["Teaching", "learn this: ... &middot; learn this (file or link) &middot; forget what you learned from ..."],
        ["Programs", "what programs do I have? &middot; learn to use ... &middot; run ... &middot; start / stop ... &middot; always allow ..."],
        ["Phone", "/status &middot; /call &middot; send me my screen &middot; is my laptop on?"],
        ["Two PCs", "what can the office PC do that you can't? &middot; on the office PC, ... &middot; get / send the skill ..."],
        ["Upgrades", "upgrade yourself so you can ... &middot; restart yourself &middot; undo the last upgrade &middot; publish the update"],
        ["Fun extras", "show me your brain &middot; open your tool armory"],
        ["Emergency", "Ctrl + Shift + F12 (stops everything until you press Resume)"],
    ]
    add(f"""
<div class="kicker">14 &middot; Cheat sheet</div>
<h1>Everything you can say</h1>
<p class="small">Start with <b>Neko</b> when you talk. You don't need the exact words - say it your way, these are examples.</p>
{table(["Topic", "Say"], rows, ["18%", "82%"])}
""")

    # 16 FAQ -----------------------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">15 &middot; Questions and problems</div>
<h1>If something isn't right</h1>
{table(["Problem", "Try this"], [
        ["She doesn't react to her name", "Say <b>Neko</b> clearly, then pause a moment. Or type in the box. Check the microphone in Windows."],
        ["She misheard a word", say("learn the word ...") + " - or type it."],
        ["Music plays but no sound", "She unmutes automatically; also check the volume and that the right speaker is selected."],
        ["Answers are slow", "Normal on the laptop's small brain. With the office PC on, she gets faster automatically."],
        ["She says she needs internet", "Command Center &rarr; Settings &rarr; tick <b>Allow internet</b> &rarr; Save settings."],
        ["The phone doesn't answer", "Is the laptop on and Neko running? Send <b>/status</b>. Check Command Center &rarr; Phone."],
        ["I lost my phone", "Command Center &rarr; Phone &rarr; <b>Unpair all</b>. In @BotFather send <b>/revoke</b> for a new key."],
        ["An upgrade broke something", say("undo the last upgrade") + " then " + say("restart yourself")],
        ["She won't do a risky thing", "That's on purpose - approve it in the window or on your phone."],
        ["Everything feels stuck", "Ctrl+Shift+F12 (emergency stop), then Resume. Or right-click the tray icon &rarr; Quit and start again."],
    ], ["34%", "66%"])}
{note("tip", "Back up weekly:", "Command Center &rarr; Diagnostics &rarr; <b>Back up now</b>. Your memory and settings are safe even if "
      "something goes wrong.")}
""")
    return document("N.E.K.O. owner's manual (laptop)", p)
