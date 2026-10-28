"""Guide 3: the everyday guide for the office PC (for the person who uses it every day)."""

from design import card, document, how_it_works, icon, note, orb, orb_states, page, phone, say, step, table, traffic_light

FOOT = "N.E.K.O. - Everyday guide (office PC)"


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
<div style="text-align:center;margin-top:16mm">{orb(95, "#ffb547")}</div>
<h1>Your AI helper<br>at the office</h1>
<div class="sub">An easy guide for the person who uses this computer every day. No computer or AI knowledge needed.</div>
<div style="margin-top:6mm"><span class="badge">Just talk to her</span><span class="badge">Safe - risky things need the owner's OK</span>
<span class="badge">Works from your phone</span></div>
<div class="tagline">Office PC &middot; RTX 5060 Ti 16 GB &middot; your assistant may have her own name (for example Nova)</div>
""", "cover")

    # 2 meet ----------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">Hello!</div>
<h1>Meet your assistant</h1>
<p class="lead">This computer has a helper called <b>Neko</b> - or the name the owner gave her when she was installed (for
example <b>Nova</b>). In this guide we write <b>Neko</b>; just use her real name instead.</p>
{how_it_works()}
<div class="grid">
{card("brain", "A strong brain", "This PC has a powerful graphics card, so she uses a big, smart AI right here. It's private: "
      "your questions don't leave this computer unless she needs the internet (weather, music, web search).")}
{card("chat", "Talk like to a person", "No special words. " + say("Neko, what's the time in London?") + say("Neko, open Excel") +
      "If she doesn't understand, she asks.")}
{card("shield", "She is careful", "Anything risky - deleting, sending, paying, shutting down - waits for the <b>owner's</b> "
      "approval. You can't break anything by asking.", "#9a5b00")}
{card("book", "She remembers", "Tell her things once and she keeps them: " + say("remember that the courier comes on Thursdays") +
      "<span class='small'>This PC has its own memory, separate from the owner's laptop.</span>")}
</div>
""")

    # 3 talking ---------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">How to talk to her</div>
<h1>Say her name, then what you want</h1>
<p class="lead">She starts with the computer and waits quietly. The glowing <b>orb</b> on the screen shows what she's doing:</p>
{orb_states()}
{step("1", "Say her name", "<p>Say <b>Neko</b> (or her real name) clearly, then your request in one go:</p>" + say("Neko, play some relaxing music"))}
{step("2", "Wait a second", "<p>The orb turns <b>green</b> while she listens and <b>violet</b> while she thinks. Then she answers out loud, with "
      "the words on screen.</p>")}
{step("3", "Keep talking", "<p>For 15 seconds after her answer you can just talk - no name needed. To stop her talking: "
      + say("Neko, stop") + "</p>")}
<div class="grid">
{card("chat", "Prefer typing?", "Click the box under the orb and type, then press Enter. Typing always works, even when it's noisy.")}
{card("eye", "Can't see her?", "After 4 quiet minutes she fades away but still listens. Say her name and she comes back.")}
</div>
{note("tip", "Tip:", "if she keeps mishearing a name, say " + say("Neko, learn the word Shapla") + " - or just type it.")}
""")

    # 4 who decides --------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">Safety</div>
<h1>Who decides what?</h1>
<p class="lead">You can ask for anything. Neko sorts every action into three colours:</p>
{traffic_light()}
{table(["You can do", "Only the owner can do"], [
        ["Chat, ask questions, get explanations", "Approve risky actions (yellow and red)"],
        ["Open apps, websites and folders; control music and volume", "Upgrade Neko or add new abilities"],
        ["Read files, make summaries and study notes", "Add new programs for her to run"],
        ["Set reminders, use saved skills", "Pair phones, change the PIN"],
        ["Run the programs the owner has taught her (they may ask the owner)", "Connect this PC with the owner's laptop"],
    ], ["50%", "50%"])}
{note("safe", "When something needs the owner:", "the owner gets <b>Approve / Deny</b> buttons on their phone and she does it as "
      "soon as they approve. The approval window on this screen says <i>Owner approves on their phone</i> - you can still "
      "press <b>Deny</b> if it's not what you wanted.")}
{note("stop", "Emergency stop:", "press <b>Ctrl+Shift+F12</b> on the keyboard. Everything stops at once until someone presses <b>Resume</b>.")}
""")

    # 5 everyday + pc control -------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">Everyday help</div>
<h1>Things to ask</h1>
{table(["Say...", "What happens"], [
        [say("explain how VAT works, simply"), "A clear answer in plain words."],
        [say("write a polite message to a customer about a late delivery"), "She writes it - copy it where you need it."],
        [say("show me how a solar panel works"), "A panel opens next to her with a picture."],
        [say("what's the weather tomorrow?"), "The weather (needs internet)."],
        [say("what's on my screen?"), "She looks at the screen and explains it."],
        [say("open Chrome") + say("open my Downloads"), "Opens apps, websites, files and folders."],
        [say("close Excel") + say("minimise Word") + say("switch to WhatsApp"), "Manages the windows."],
        [say("volume up") + say("mute") + say("unmute"), "Sound control."],
        [say("in Calculator click Seven") + say("what buttons are in this window?"), "She presses buttons inside apps by their names."],
        [say("lock my PC"), "Locks the screen when you leave the desk."],
    ], ["52%", "48%"])}
{note("info", "Asking, not ordering:", "you never need exact words. Say it your way - if she isn't sure, she asks you.")}
""")

    # 6 music, files, reminders ------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">Music &middot; files &middot; reminders</div>
<h1>Make the day easier</h1>
<div class="grid">
{card("music", "Music", say("play some Bangla songs") + say("pause") + say("resume") + say("louder") + say("play next") +
      say("stop the music") + "<p class='small'>When a song ends, the next one starts by itself. While music plays, "
      "<i>pause</i>, <i>skip</i> or <i>stop</i> work without her name.</p>")}
{card("file", "Files and PDFs", say("read the price list pdf") + say("summarize this") +
      say("make simple notes and a cheat sheet from this PDF") +
      "<p class='small'>Click a file in File Explorer first, or say its name - she looks in the allowed folders.</p>")}
{card("bell", "Reminders", say("remind me at 4 to call the supplier") + say("remind me in 30 minutes to check the oven") +
      say("what are my reminders?") + "<p class='small'>She says it out loud - and messages your phone if it's paired.</p>")}
{card("book", "Teach her", say("learn this: the delivery van is the white Toyota, number 12-3456") +
      say("remember that Mr. Karim pays on the 5th") +
      "<p class='small'>She uses it later when you ask. The owner can see and remove what she learned.</p>")}
</div>
""")

    # 7 programs & skills ----------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">Programs and shortcuts</div>
<h1>Your work programs, by voice</h1>
<p class="lead">The owner can teach Neko the shop's programs (for example the billing software). Then you can just ask:</p>
<p>{say("which programs can you run?")} {say("open Print SOFT")} {say("stop Print SOFT")}</p>
<p class="small">Some programs ask the owner for approval each time; others the owner has marked as always allowed.</p>
<h2>Saved skills - many clicks in one sentence</h2>
{step("1", "Show her once", "<p>Ask her to do the steps one by one, for example:</p>" + say("open Print SOFT") +
      say("in Print SOFT click New bill") + say("click Today"))}
{step("2", "Save it", say("save that as start a new bill"))}
{step("3", "Next time", say("do start a new bill") + "<p class='small'>She repeats all the steps. " +
      say("what skills do you know?") + " shows the list.</p>")}
{note("tip", "Good to know:", "skills can also come from the owner's laptop - the owner can send useful skills to this PC.")}
""")

    # 8 phone -------------------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">On your phone</div>
<h1>Talk to her from your phone</h1>
<div class="row" style="align-items:flex-start">
<div class="col">
<p>If the owner paired your phone as an <b>everyday phone</b>, you can chat with Neko in <b>Telegram</b> - from anywhere:</p>
<ul>
<li>Type, or send a <b>voice note</b> - she answers with a voice note.</li>
<li>Send a <b>photo</b> with <i>what is this?</i></li>
<li>Send a <b>PDF</b> with <i>summarize this</i> (it's saved on the office PC).</li>
<li>{say("remind me at 6 to lock the shutter")} {say("play music on the PC")} {say("send me my screen")} (asks the owner)</li>
<li><b>/status</b> - is the office PC on? &nbsp; <b>/call</b> - a voice call with her (needs Tailscale).</li>
</ul>
{note("safe", "Risky requests:", "she asks the owner on their phone and tells you she's waiting. You can't approve, and you can't "
      "upgrade her or change her settings from your phone.")}
</div>
<div style="flex:0 0 66mm">{phone("Office Nova", "bot", [("me", "print yesterday's sales report"),
        ("bot", "That needs the owner's OK - I've asked them."), ("bot", "Done - the report is printing.")])}
<div class="figcap">Everyday phone: risky things wait for the owner.</div></div>
</div>
""")

    # 9 cheat sheet ----------------------------------------------------------------------------------------------------
    rows = [
        ["Talk", "Neko, ... &middot; Neko, stop &middot; Neko, wait - ... &middot; learn the word ..."],
        ["Questions", "explain ... simply &middot; show me ... &middot; what's the weather? &middot; what's on my screen?"],
        ["Remember", "remember that ... &middot; forget ... &middot; learn this: ..."],
        ["Computer", "open ... &middot; close ... &middot; minimise ... &middot; switch to ... &middot; volume up/down &middot; mute &middot; unmute &middot; lock my PC"],
        ["Inside apps", "in ... click ... &middot; in ... open File > ... &middot; what buttons are in this window?"],
        ["Music", "play ... &middot; pause &middot; resume &middot; louder &middot; quieter &middot; play next &middot; skip &middot; stop the music"],
        ["Files", "read the ... pdf &middot; summarize this &middot; make notes and a cheat sheet from this PDF"],
        ["Reminders", "remind me at ... to ... &middot; in 20 minutes ... &middot; what are my reminders? &middot; cancel my reminders"],
        ["Programs", "which programs can you run? &middot; open / run ... &middot; stop ..."],
        ["Skills", "save that as ... &middot; do the ... &middot; what skills do you know?"],
        ["Phone", "/status &middot; /call &middot; send me my screen"],
        ["Voice", "use a male voice &middot; switch to female voice &middot; speak Bangla &middot; speak English"],
        ["Emergency", "Ctrl + Shift + F12"],
    ]
    add(f"""
<div class="kicker">Cheat sheet</div>
<h1>Quick list of things to say</h1>
<p class="small">Start with her name. These are only examples - say it your way.</p>
{table(["Topic", "Say"], rows, ["18%", "82%"])}
<div class="row" style="margin-top:4mm">
<div class="col">{note("tip", "Stuck?", "say " + say("Neko, what can you do?") + " - she explains her abilities.")}</div>
</div>
""")

    # 10 FAQ --------------------------------------------------------------------------------------------------------
    add(f"""
<div class="kicker">Questions</div>
<h1>If something isn't right</h1>
{table(["Problem", "Try this"], [
        ["She doesn't react", "Say her name clearly and pause a moment. Or type in the box under the orb."],
        ["She heard the wrong word", "Say it again more slowly, type it, or " + say("learn the word ...")],
        ["She says it needs the owner's OK", "That's normal for risky things - wait for the owner, or ask them."],
        ["No sound from music", "She unmutes the PC herself; also check the speakers are on."],
        ["She says she needs internet", "Ask the owner - internet is switched on in her settings."],
        ["My phone gets no answer", "Is the office PC on? Send <b>/status</b>. If you got a new phone, the owner must pair it again."],
        ["She did something wrong", "Say " + say("Neko, stop") + " - or press Ctrl+Shift+F12 to stop everything."],
        ["An update is offered", "The small Neko icon near the clock &rarr; <b>Install update</b> (or leave it for the owner)."],
    ], ["36%", "64%"])}
{note("info", "Privacy:", "what you say is not recorded. Conversations and memories stay on this PC. The owner can see what she "
      "did (her activity list) and what she remembers.")}
""")
    return document("N.E.K.O. everyday guide (office PC)", p)
