# Book of Work

**Where this stands (2026-08-26): nothing is open.** Every item has been
built, or closed with the evidence that it no longer applies -- including
the last structural one, "sections as pure containers", which
`tools/parity_check.py` showed has no observable payoff left (30 tools,
0 differences between a section and a cell). What remains under an
"Open:" heading below is either struck through, a finding rather than a
task, or the reasoning an entry was built from. Add new items here the
same way: with a date and enough context to act on without re-deriving
the reasoning.

Product/design/content backlog — things identified as worth doing but not
yet built or scheduled. Unlike CLAUDE.md's "Deferred follow-ups" (which is
architecture decisions explicitly set aside), this is open work: pick an
item, scope it, do it. Add new items with a date and enough context that
a future session can act on it without re-deriving the reasoning.

## 2026-08-26 - A tab that said one business and a Terms page that said another

Found by looking at the finished site rather than at a check: the browser
tab read "Riverstone Coffee Roasters" while the page under it was a
bakery and its Terms & Conditions named "Flour & Salt". One install, one
website, two names -- `site_title` and `legal_business` -- and nothing
had ever made them agree.

The banner added earlier that day did NOT fire, and was right not to:
"Riverstone Coffee Roasters" is not any installed template's example
name (the coffee shop's is "Riverside Roasters" -- the site was carrying
a name from an older revision of that template). The app cannot prove
that is not the owner's own name, and must not overwrite one it cannot
prove.

So the fix is not to merge them:

- **The legal name falls back to the site's** when it is blank, instead
  of standing empty beside it.
- **The Legal screen says which it will use**, and says why you might
  fill it in anyway: a trading name and a legal entity are genuinely two
  things.
- **A disagreement is pointed out, not resolved.** "Your site is called
  X but these pages say Y. That is fine if the legal entity really is
  different -- otherwise clear this box, or change the site's name."

Two names that disagree is sometimes right and sometimes a leftover, and
only the owner knows which. What is not acceptable is shipping both
without mentioning it.

## 2026-08-26 - Thirty tools, both containers, no differences

"One renderer per tool" was always checked by reading. `tools/parity_check.py`
checks it by rendering: every tool goes on a page of its own TWICE --
once as a section, once as a cell of a Columns section -- and the two
editor panels are compared with the things that legitimately differ
taken out.

What is taken out is itself the answer to what phase 4 has left:

- **ids and URLs**, which name the container;
- **`data-corner-field`**, because a section has its own corner AND its
  tool's (`tool_corner_style`) while a cell has only the tool's
  (`corner_style`) -- the same control writing to a differently-named
  field. That is the whole residue of "sections as pure containers", and
  it is invisible to whoever is using it;
- **the remove button's wording and its confirm**, which SHOULD differ:
  removing a tool that is its own section deletes the section and cannot
  be undone; clearing a cell leaves the cell.

**Result: 30 tools, 0 differences.** Getting there found three real ones,
none of which anybody had noticed by reading:

- The **Contact Form**'s panel explained itself in a cell ("Messages go
  to your Email Settings address") and said nothing at all as a section.
- The **File** tool's display select defaulted to Card when unset in a
  cell and to nothing as a section.
- The **Media Player** in a cell offered an upload button where the same
  tool as a section offered the YouTube link box -- because "unset"
  reached the branch as "not youtube" in one container and as the
  column's default in the other.

**The check took as many attempts as the refactor**, and each failure was
its own kind of wrong: pairing panels by position compared every tool
with the next one along (33 of 33 "differ", which is the sort of result
that should make you check the check); pairing by label could not tell
four Text panels apart; and taking "the first panel on the page" got the
site's header Menu, because the page shell renders the header's tools
first. It pairs by the ids inside each panel now, falling back to the
panel inside the section element for a Text tool, whose toolbar carries
no URL at all.

**What this closes.** The remaining phase 4 step -- `sections.type` going
away so a section stores its tool the way a cell does -- was justified by
tools behaving differently in the two containers. They no longer do, and
the one asymmetry left is a field NAME. So the schema step is now a
tidiness change with no observable payoff, and this is the evidence for
leaving it alone rather than the assumption that it is fine.

## 2026-08-26 - One list of tool controls

With the routes merged, the markup could follow: both the section chain
and `render_cell` wired the same nineteen `*_config_fields` macros inside
the same forms, differing only in the item's name, a column index and a
`?row=` suffix. One macro now, two callers, and 268 lines of template
gone.

**Three attempts, and the first two are the interesting part.** A
line-based rewrite of all nineteen cell branches in one pass produced
markup that rendered for VISITORS -- 2.8 KB in the view that has no
controls in it at all -- because the branches come in three shapes: the
whole call on one line, a call wrapped onto a second line, and a call
opening on the same line as `{% if editing %}`. Each shape broke it
differently. The third attempt did it in verified steps instead:

1. **The macro, then the section side alone.** If the render check stays
   byte-identical, the macro reproduces that side exactly -- which it did,
   once the call's own whitespace was trimmed on the left only. Trimming
   neither left a blank line per section; trimming both removed one.
2. **Then the cells**, one branch at a time.
3. **Then the guards trimmed**, because nineteen `{% if %}`s emit a
   newline each even when false: inline that cost nothing, shared it gave
   a Text cell twenty blank lines.

**Byte-identity was not achievable after step 3, and should not have
been** -- the whitespace between tags genuinely changes. So the check
became "identical once whitespace is collapsed", done by splitting both
renderings into tags and diffing the sequences. The visitor's view stayed
byte-identical to the baseline throughout (`da13dd79`, 50403 bytes); the
editing view came out **13,582 tags against 13,581, one hunk**.

**That one hunk is the twenty-ninth tool.** The Contact Form's panel in a
CELL said "Messages go to your Email Settings address. Nothing to
configure here." and the same tool as a SECTION said nothing at all --
an empty panel staring back. Sharing the list gave it the hint in both
places. A second difference the merge exposed did not even reach the
rendering: a File tool's display select defaulted to Card when unset in
a cell and to nothing in a section, and the cell's rule was the right
one.

So the merge did what the whole "one renderer per tool" item was for:
the last two places where the same tool behaved differently depending on
which container it was standing in are gone, and they were found by the
merge rather than by looking.

Verified afterwards: placement matrix 570 of 570, uploads 19/19,
newsletter 67/67, sign-up 26/26, fresh install 23/23, and the live site's
editor rendering every tool panel on all six pages with none of it
reaching a visitor.

## 2026-08-26 - What a new install actually opens on

"Clean it up to the standard of a shippable product." The clean-up part
was small; what it turned up was not.

**A brand-new install opened on a blank page.** One page, two placeholder
sections, the words "Edit this page from the admin dashboard", no
template active -- and sixteen ready-made looks sitting in a library
nobody had been sent to. For a product whose entire pitch is those
sixteen looks, that is the worst possible first screen, and it is not
what they are for.

A first boot now opens the site with one on: its pages, its layout, its
header and footer, and its own name until the owner sets theirs. Six
pages and a footer instead of a stub. Two things about how it is
guarded:

- **On first boot, not on "nothing looks active".** The difference
  matters: an existing site upgrading to this version must never have a
  template applied over what somebody has written. It runs only in the
  branch that has just created the home page -- by definition a site
  with nothing in it.
- **After the blueprints are registered, not inside the seed.** Applying
  a look builds the site's menus, and a menu asks `url_for` where each
  page lives; the seed runs before there is a `public.home` to ask
  about. It failed exactly that way first.

**And the name it opens with says it is borrowed.** A site that starts
with a look also starts with that look's example business name. Rather
than let somebody ship "Miller Family Landscaping", every admin screen
carries a line saying so until the owner replaces it -- and the question
"is this name still an example?" is now asked in one place
(`demo_identity_names`) instead of being rebuilt inside
`_apply_pack_identity`.

**`tools/fresh_install_check.py`** is the new net: it boots against an
empty data directory, twice, and asks the questions a first five minutes
would. All sixteen templates present with one active, a site to look at
with every page rendering, every admin screen opening, and nothing
carried over from here -- no subscriber, no order, no address, no key,
no theme directory that is not in the library, and no duplicate row on
the second boot. 23 checks.

Its first run reported four failures and **two of them were the check's
own fault**, which is worth recording because both are traps for the
next one: Google credentials in the settings are the ENVIRONMENT being
adopted on first run exactly as designed, not a leak; and a theme
directory left over from the live site is not a fresh install's problem,
because `themes/` is its own mounted volume and is not inside DATA_DIR.

**A lesson from the clean-up itself.** Deleting the nine orphan theme
directories was judged against the live site's library -- and the render
check's own throwaway site, which shares the same container and the same
themes folder, had one of them as ITS active template. Nothing broke,
but "orphaned" is a question that has to be asked of every site sharing
a folder, not just the one in front of you.

**The render check stopped counting the picture library as rendering.**
That is what surfaced the above: the editing view lists every uploaded
file and every picture the active template brought, so uploading
anything or deleting a stray folder moved the whole-page hash while
nothing rendered differently. It cost two investigations before it was
normalised, alongside the cache-buster and the captcha token.

## 2026-08-26 - Cover flow and a deck of cards

The last two Image Accordion displays, open on the backlog since the
Carousel and Masonry pass. Same rule as those three: **the panels are
identical in all five and only the container's class changes**, so
switching display can never lose a picture or a caption.

**Cover flow** holds one picture at the centre with its neighbours angled
away behind it. The angle cannot be written in CSS alone, because CSS
cannot ask "how far is this panel from the middle of its scroll
container" -- so the script answers exactly that, as one number per
panel (-1 at the left edge, 0 in the middle, 1 at the right), and every
angle, scale and fade is ordinary CSS reading it. The look stays in the
stylesheet; move the numbers there and the script keeps feeding it.
Underneath it is the same snap track the Carousel uses, so a phone
swipes it natively, and it gets the same injected prev/next arrows.

**Deck** is a pile of photographs; clicking the top one sends it to the
back. The order is a number per panel rather than a reordering of the
DOM, so looking at a gallery never touches the markup saved in the
section -- the same rule the Carousel's arrows follow. Only the front
card is in the tab order and readable to a screen reader; the ones
behind it are decoration until they come round.

Three things worth keeping from doing it:

- **The hover rules stopped naming every style that is not them.** They
  were three selectors reading `:not(carousel):not(masonry)`, so adding
  a fourth display meant remembering to extend all three -- and
  forgetting would leave the new display fighting the hover effect.
  `:not([class*="cms-accordion-style-"])` asks the question once, and
  still treats content saved before any of this existed, which carries
  no style class at all, as the default.
- **The front card is named, not inferred.** The caption rule was keyed
  on `[style*="--cms-deck: 0"]`, which worked only because Chrome
  happens to serialise a custom property with a space after the colon. A
  browser that did not would have shown all five captions stacked on one
  another. It is a class now.
- **`abs()` has a fallback.** A browser without it gets the flat snap
  track rather than a broken transform.

Measured in a browser rather than eyeballed: the cover flow numbers rise
left to right, the centre panel's is nearest zero, they follow the
scroll, and the transform really lands (a matrix3d, not `none`); the
deck's front moves to the back on a click, only its caption shows, and
the pile keeps its shape at 375px with nothing scrolling sideways.

## 2026-08-26 - The last seventeen pairs, and the one that stays

Finished the route-pair collapse: **32 of 33**. The second half was the
family where a FILE arrives, which shared less than the first -- so two
more things became shared before the routes could be.

**One place a file is taken in.** Three routes wrote the whole thing out
-- choose the file, `secure_filename`, check the extension against an
allowlist, generate a unique name, make the folder, save -- and a fourth
would have written it again. `_saved_upload` is that, once. It is also
the rule CLAUDE.md states about uploads, in one place instead of three
places that could each drift.

**A tool's own fields.** `_Where.write` takes them by name now, because
that is the real asymmetry between the two containers: a section keeps
`title`, `file_size` and `media_type` in its own columns, a cell keeps
them as keys in its dict. An upload route no longer has to know which it
is standing in.

**The one that stays a pair is `update`**, and it is worth saying why
rather than leaving it looking unfinished. The other thirty-two were two
copies of one thing. This one is two different field sets sharing a
name: a section writes its own columns -- including a background picture
and a border colour that a cell has no notion of -- while a cell writes
dict keys, and a section has both its own corner and its tool's where a
cell has only the tool's. Merging those would mean a table of which
field means what in which container, which is phase 4's job (sections as
pure containers), not this one's.

**A picture applied to an Accordion panel is now adopted**, which is a
small behaviour change made on purpose: every other Library-picker button
in the app copies a template's picture into the site's own uploads first,
so the page keeps it when the template is deleted. The two accordion
routes were the only ones that did not.

**And a new net, because the old ones could not see this.** The render
check proves the markup did not move and the placement matrix proves
every tool still draws itself in every container -- but neither posts a
FILE. `tools/upload_check.py` walks a real upload through both
containers: the picture lands, the row or the cell points at it, the file
is on disk, an executable is refused in both, a missing file is refused,
a download keeps the name it arrived under and its size, and an mp4 and
an mp3 are told apart.

Writing that check produced the day's neatest small lesson: on its first
run it uploaded into the REAL uploads folder, because `UPLOAD_FOLDER` is
a path in the image rather than something `DATA_DIR` moves -- and every
Image Library picker on the site then offered a 1x1 test PNG. The render
check caught it as a 980-byte growth in the editing view, and `--dump`
(added yesterday for exactly this) turned "something moved" into a diff
naming the files. The check now points `UPLOAD_FOLDER` at its own
directory.

## 2026-08-26 - Fifteen pairs of routes become fifteen routes

The backlog's biggest open item: every "update this tool" route existed
twice, once for a tool standing as a section and once for the same tool
in a Columns cell. The interesting half -- working out what the new
markup should be -- was already shared. The dull half was not: each pair
differed only in where the markup is read from and written back to.

So that is now an object. `_Where` is a section or a cell, with `read`,
`write` and `respond`, and a route is one function registered on BOTH
URLs -- Flask takes two `@bp.route` decorators, and `url_for` with
`col_index=None` builds the section URL because Flask drops None values.
So the URLs did not change at all; only the endpoint NAMES did, and the
templates' `X if col_index is not none else Y` ternaries collapsed to one
call each.

**Fifteen pairs**: Menu, Breadcrumb, Divider, Search, Blog, Basket, Shop,
Buy Button, FAQ, Contact Info, every declared block, Banner, Card,
Accordion, Video Gallery.

Three things fell out of doing it:

- **The tool is always named now.** Three cell routes used
  `setdefault("tool_name", ...)`, which is wrong on a cell that was
  blank: `_normalize_cell` gives an empty cell `tool_name: ""`, which is
  present, so the name never landed and the panel showed a tool with no
  name.
- **A cell holding a tool is `html`.** Some cell routes set the type and
  some did not, and a cell whose content is a tool's markup but whose
  type says "text" gets offered a bold/italic ribbon.
- **The reply is per-tool, not per-route-shape.** A Menu hands back
  `content` for the live nav, a Contact block and a declared block hand
  back `html`, a Banner hands back the class and style its wrapper should
  carry. That is now an argument rather than four almost-identical JSON
  branches.

**The first attempt broke it, and the net caught it in one run.** The
replacement cut from the section route to its cell twin and pasted over
the span -- which assumes the two are adjacent. They are not:
`block-update` sits between `buy-update` and its twin and was deleted, so
the page 500'd on a missing endpoint the moment the render check ran. The
second attempt replaces each function where it stands. Worth recording
because the tempting shortcut is exactly the one that fails, and because
this is the whole argument for having built the check first.

Both nets clean afterwards: the render check byte-identical (same URLs,
same markup) and the placement matrix 570 of 570.

Eighteen pairs left, all in the family where a FILE arrives -- upload,
AI generate-and-apply, banner and card pictures, an accordion panel, a
gallery clip -- plus the generic `update`. They share the write half now,
so what is left of each is the upload itself.

## 2026-08-25 - A footer that describes three columns and builds three

Backlog item, noticed while checking that the footer presets really
applied and deliberately left alone at the time. Both the Columns preset
("menu links, contact & social icons, a closing note") and the Centered
one ("a centered menu with contact/social icons beneath it") describe a
contact column, and applied by hand both built two cells: menu and
copyright. The third only appeared when a TEMPLATE supplied contact
details in its manifest.

The reason recorded at the time was that there was no real contact
information to seed. That stopped being true: the site's own details are
on file from the Legal pages screen, and they belong to the site rather
than to whichever template is being tried on -- so the manual route now
builds the contact column from the site's own phone, email and address.

With nothing on file it builds the column anyway, empty, carrying the
Contacts tool's own "add a phone number, email, address or social link"
prompt. An empty column asking to be filled in is a truthful third
column; a missing one is not.

Simple is untouched, because Simple describes one menu row and builds
one.

## 2026-08-25 - An email that looks like the site it came from

The last two pieces of the newsletter plan, and both are mostly about
being honest concerning what an inbox can do.

**The site's colour travels; its typeface does not.** The email sheet was
a hardcoded grey card with one blue for links, so a bakery in terracotta
sent exactly what a clinic in navy sent. It now takes the active
template's resolved primary -- the owner's override winning over the
palette the template shipped with -- for links, quote rules and table
heads, with a pale wash of the same colour behind the card. What it does
NOT do is pretend about two things:

- **Fonts.** Gmail strips `@font-face`, so a self-hosted webfont never
  loads. What can travel is the FALLBACK already declared in the theme's
  own stack -- "Georgia, serif" against a system sans is a real,
  visible difference, and it is the truthful half.
- **Dark grounds.** Several clients invert colours themselves and
  Outlook will not draw a border-radius at all, so the card stays light
  whatever the site does. A dark email is where "themed" turns into
  "unreadable in somebody's client".

Resolving a template's colours moved from `routes/public.py` into
`services/palette.py` on the way past. It was a private helper for the
Colors panel; the newsletter needed the same answer, and a route may not
reach into another route.

**The greeting and the sign-off are the owner's. The footing is not.**
Two plain-text fields wrap every send -- page or post -- with two
placeholders (`{{title}}`, `{{link}}`), blank lines making paragraphs,
and no raw-HTML box anywhere, because there is no raw-HTML box anywhere
else in this app for something an owner writes. A mistyped placeholder
is left as typed rather than vanishing: it should look like a mistake.

Under the two boxes sits the part that cannot be edited, shown greyed
out rather than left off the screen -- the postal identity and the
unsubscribe link. Hiding them invites the assumption that they are
missing; showing them says plainly that they are not going. A template
that could delete them would be a template that could break the law.

`tools/newsletter_check.py` is at 67. The two colour checks failed at
first for a reason worth keeping: the accent is spent on links, headings
and rules, and the test letter had no link in it, so there was nowhere
for a colour to appear. The check now puts one there.

## 2026-08-25 - A post is already an issue

"How about blog being the content of newsletter emails?"

Right, and it makes the thing I proposed an hour earlier -- a masthead
block, an issue date, sections grouped under it -- redundant before it
was built. A post already has every part of that: a title, a date, a
permanent address built from its blog's slug so it survives the site
being rearranged, and an online copy for the "read it online" link. The
newsletter page was rebuilding a blog post, badly, on a page.

**The tell showed up immediately, and this codebase has met it before.**
`newsletter_sends.page_id` was `NOT NULL REFERENCES pages(id)`, which
was fine while a newsletter could only be a page -- and the moment a
post can be sent, that column points at the wrong owner. It is the same
sentence CLAUDE.md already carries about `blog_posts.page_id`: **a
column pointing at the wrong owner is the tell that a feature has been
modelled as a page.** So the table was rebuilt around a kind and an id.

The foreign key did not come back, deliberately. A record that you
emailed forty people should outlive the page being deleted -- that is
what the record is FOR -- so history joins outwards and falls back to the
subject it stored, and the public archive lists only what can still be
read while the history keeps everything that was sent.

Two smaller things worth the words:

- **One send, two callers.** The page send's checks were interesting and
  none of them was about pages: something to send with, a postal address
  on file, somebody to send to once the audience is applied, and content
  at all. Extracted first, THEN the post route written against it --
  which is why the post send needed no new guards and cannot drift from
  the page's.
- **A draft is published first, and says so.** Sending is not
  publishing, but an email whose "read it online" link answers Not Found
  is worse than either. The button reads "Publish and send" and the
  confirm says which.

`post_html` moved from `routes/public.py` into `services/blog.py` on the
way past: a post's plain-text paragraphs becoming HTML was a private
helper in a route, and a route may not reach into another route.

52 checks now in `tools/newsletter_check.py`, including that a draft's
preview promises no online copy, that sending publishes it and the link
then works, and that deleting the post afterwards keeps the record of
having sent it.

## 2026-08-25 - Customers are a fact, not a list to keep up to date

"We may want to give some users preferential offers, like frequent
customers. They may need different content from what is publicly
available. How would I manage that?"

The content half was already there and neither of us had noticed: a page
with "people can read this page on the site" turned off, built earlier
the same day, IS content that goes to the list and never appears on the
website. So public issues are pages anybody can read, members-only
offers are private ones, and the send is the same send.

What was missing was the WHO, and the shape of the answer matters more
than the feature. **Being a customer is not a label to maintain; it is
something the site already knows.** `customers` have addresses and
`orders` have statuses, so "has this person paid for something" is a
query, asked live, and there is no list that silently goes stale the
moment somebody buys. A refunded order stops counting, because a refund
rewrites the status -- so one purchase since refunded does not make
somebody a customer, and four purchases with one refund still does.

Two things it cannot know, so two deliberate additions:

- **The owner's own answer.** A sale in the shop, an order by telephone,
  or somebody who signed up with one address and bought with another --
  all real customers this site never saw. That is a star on the row.
  It ADDS to what the orders say and never vetoes it: unflagging
  somebody who really did buy leaves them a customer, because they are
  one, and the screen says so before you press it.
- **Which way a send is aimed.** Everyone, or the customers among them,
  chosen on the page's own bar and on the Newsletters screen, with the
  count beside each so the confirm names the number it will actually
  reach rather than the number on the list. The history records it too:
  "sent to 40" cannot say whether that was the whole list or the
  customers on it, and that is the first thing anybody asks a month
  later.

**The rule that does not bend**: a customer is not a subscriber. Somebody
who bought and never confirmed a subscription is not written to, however
good a customer they are -- the audience is always an intersection with
the confirmed list, which is the whole point of the double opt-in built
this morning. Refusing a customers-only send says the true thing, too:
"nobody on the list has bought anything yet", not "nobody is on the
list", when there may be plenty of people on it.

Worth writing down because it will come up: **a private page is not a
secret.** The email can be forwarded, screenshotted or posted anywhere.
Keeping the page off the site is what makes an offer feel like an offer;
if one must not be shared, the enforcement belongs on the code -- a
per-person token or a cap at Stripe -- not on the page being private.

`tools/newsletter_check.py` covers it: 39 checks now, including that the
address match ignores the case it was typed in, that a refund takes the
status away, that flagging adds and unflagging does not subtract, and
that a customers-only send reaches exactly one of two subscribers.

## 2026-08-25 - The newsletter stops being a kind of page

"The newsletter page should follow the convention as other pages. It
should be optional to add it to the site so recipients can view it live.
The page should auto-populate with text body when created. The user can
add many sections and choose which section to email, by number or latest.
Admin can see preview and send it from the newsletter page."

Five sentences, and between them they take the last real page TYPE apart.
Newsletter was defended in CLAUDE.md as the one that earned its place: it
did not carry a feature, it changed what the page WAS to the rest of the
app -- kept out of the navigation, listed in the public archive, sendable
to a list. That defence was three claims wearing one coat, and pulling
them apart is the whole of this change.

**Kept out of the navigation** was never about newsletters. A page is in
a menu because somebody ticked it in the Menu tool; nothing has to be
excluded by kind for a year of issues not to pile up in the header. The
exclusion is gone and nothing filled up.

**Listed in the public archive** was the owner's decision being made for
them, which is what "it should be optional" says. Whether people can read
a page is a question EVERY page has, so it is now `pages.is_public` --
off means a visitor gets Not Found, the owner still opens and edits it,
it is left out of the navigation and the archive, and an email sent from
it carries no "read it online" link, because there would be nothing to
read. An issue can go only to the list, or be a page anybody can link to.

**Sendable** is what is left, and it is an action, not a kind. So
`page_type='newsletter'` is now a marker about what the OWNER sees: a
Subject, a Preview and a Send at the top of the page while editing, and a
line on the Newsletters screen. Any page can be one; one can stop being
one; the writing stays put either way.

Then the three practical things:

**It arrives with something to type over.** "Newsletter" is a starting
layout now, like Blog and FAQ, and it starts as one Text tool with the
shape of an issue in it -- which also retired the tick box on the new-page
form that asked the same question the starting point already asks.

**A send can be aimed.** Everything on the page, just the latest, or one
section by number. That needed sections to know when they last changed,
which is a trigger rather than a column the code remembers to write:
there are a dozen routes that update a section and a rule kept in the
database cannot be forgotten by the thirteenth. It stamps to the
MILLISECOND -- with `CURRENT_TIMESTAMP`'s whole second, three sections
written in the same second tie, and "latest" quietly fell back to the
highest id, which is the newest ADDED rather than the most recently
CHANGED. The test caught that on the first run.

**Preview and Send are on the page.** Both take the same aim, because a
preview of something other than what will send is not a preview.

`tools/newsletter_check.py` walks all of it on a throwaway site with the
mail captured rather than sent: 28 checks, including that a visitor gets
404 on a private page while its owner does not, that the email from one
promises no online copy, and that the send lands back on the page it was
sent from.

And the render check's new `--dump` paid for itself immediately. The
whole-page hash moved by six bytes in both views; instead of an hour of
guessing, the diff was two blank lines left by an `{% if %}` that is
false on every page that is not a newsletter.

## 2026-08-25 - Three things wrong with the Menu on a phone

"I cannot see the pages in the menu bar in mobile view", then, after the
first fix, "menu is still difficult to manage". The second was right: the
first fix was real but only a third of the problem.

**The list hung off the side.** "Items (5)" opened a 200px popover
anchored to a button already near the right edge of a 390px screen, so
what you got was a column of tick boxes with the page names cut off --
the one part you need to read. On a phone it now takes a line of its own
in the panel, full width, rather than floating; there is nowhere sensible
for a floating 200px panel to hang on a 390px screen. The icon grid,
which is placed in script relative to the picker, flows there too --
`position: static` ignores the `left` the script sets, so nothing in the
script had to learn about this.

**A popover could still open past the edge on a wide screen**, because
the panel can be as narrow as the column the tool is standing in. So the
script slides one back until it fits, which took six lines and covers the
icon grid as well.

**And then the panel itself would not shrink.** This is what the second
message was about, and it took measuring rather than reading: with the
list open, the whole chain from `.cms-tool-header-controls` down measured
431px wide on a 375px screen, so the panel scrolled sideways -- tick
boxes off one edge, "+ Page" off the other. Two causes, neither of them
the list. The picker is a flex item, and a flex item does not shrink
below its own content unless told to. And the two "add" rows inside it --
new page, custom link -- are single-line flex rows whose text inputs
carry a browser's default twenty-character width; 409px of demand on a
375px screen. Wrapping them so each input takes a line is what fits.

Measured afterwards at 375px, from the stylesheet rather than from an
injected patch: nothing on the page wider than the screen, no sideways
scroll, all six page names readable, every tick box on screen, and all
three of + Page, + Link and + Divider reachable.

**How it was measured** is worth keeping. The editing view needs a login
and the browser would not accept a minted session cookie, so the panel's
own markup was pulled out of a real editing render and served as a
standalone page from the container's static folder with the real
stylesheets linked. Same markup, same CSS, no session -- and every number
above came from the real thing rather than a guess about it.

## 2026-08-25 - A legal page with two headings and a code box

Two things, both in what the Legal pages screen writes.

**Every document had its heading twice.** Putting them all on one page
gives each an anchor, and the way that was done was to prepend
`<h2 id=slug>Title</h2>` -- while every document template already opens
with its own `<h2>` saying exactly the same words, since both come from
the same registry. So "Cancelling and refunds" appeared twice, one line
under the other, on every document on the page. The anchor now goes ON
the heading the document already has. A migration removes the repeat from
pages already written, and only where the two really do say the same
thing and stand next to each other -- two `<h2>`s further apart are the
document's own structure and none of a migration's business. The id moves
to the survivor, so existing links still land.

**And it was written as an HTML/Embed.** That is the fourth or fifth time
this rule has had to be applied, and the rule is in CLAUDE.md: Embed is
for markup that genuinely has to be markup -- a booking widget, a payment
button. A refund policy is prose. As an Embed, an owner opening their own
terms got a `</>` code box, which is this app's marker for "third-party
script goes here". They are Text tools now, with bold, italic and a
heading button like every other piece of writing on the site, and the
four already on this site were moved across.

Worth being precise about why this kept happening: `type='html'` is not
the Embed tool. It is the generic carrier for almost every tool's markup
-- Menu, Blog, Contact Form and the rest are all `html` sections wearing
an identity class, and the renderer dispatches on that class. A section
with none of those classes falls through to the Embed branch. So writing
prose into an `html` section with no marker does not read as "plain
HTML"; it reads as "the admin pasted in third-party code". The test for
anything generated is not what column it goes in, it is which tool the
owner will find when they click it.

## 2026-08-25 - Proving the list survives, rather than assuming it

"Is all this kept through a restart, and is it in the backup?" It was,
and it is -- but neither had been demonstrated, and an email list is the
one thing in this database that cannot be typed again. A page can be
rewritten. The people who agreed to hear from you, and the record of
them agreeing, exist here and nowhere else.

`tools/persistence_check.py` now shows it, against a site of its own so
no real list is touched. It puts a confirmed subscriber on that site,
takes a backup, reads the table straight out of the archive, empties the
live list, restores, and compares every column of the consent record --
the wording, the page, both IP addresses, both timestamps, and the
unsubscribe token, since a restore that changes the token silently
breaks the link in every mail already sent. Then the container is stopped
and REMOVED, brought back, and the row is looked for again: 21 checks,
then 5.

Two things were actually missing. The backup manifest counted pages,
orders, bookings and files but not subscribers -- so the one thing worth
checking before trusting an archive was the one thing the archive would
not tell you. It counts them now, and the Backups screen says "N on the
email list" beside each entry. And what the archive deliberately does
NOT carry is worth stating in the same breath: not the encryption key,
so a copy of it cannot spend your money.

## 2026-08-25 - A sign-up that never mentioned the second half

Five things wrong with one form, found by using it.

**It did not say a confirmation email was coming.** Sign-up here does not
put anybody on a list -- it sends a mail with a link, and only the link
does. Somebody not told that has no reason to look for it: they fill the
form in, see a thank-you, and never hear from the site again, having done
nothing wrong. The block says so now, before it is used, in wording that
is deliberately NOT an editable field. Everything else in the block is
the owner's to write; this one sentence describes how the mechanism
behaves, and an owner rewording it into "you are now subscribed" would
make the site lie about its own process.

**The answer arrived where nobody was looking.** The form posted
normally: page thrown away, rebuilt, scrolled to the top, answer as a
line up there. Measured on this site's own home page, the sign-up sits
1994px down a 2380px page -- so the one message somebody MUST see was
put two thousand pixels above where they were standing, after a reload.
It posts itself now and writes the reply into its own box. Every check
is still on the server, which still redirects a plain form post, so no
script means no change. The words come from one place (`SIGNUP_MESSAGES`)
rather than being written out in both.

**Confirming sent nothing.** Following the link showed a web page and
that was all, so somebody could subscribe and then hear nothing for six
months, having never been given a way out. Confirming now sends a
welcome that carries the unsubscribe link -- in the text, and in
`List-Unsubscribe`/`List-Unsubscribe-Post`, so a mail program can offer
its own button. That header pair is why `/unsubscribe/<token>` answers
POST as well as GET, and why it is the sole member of a new, explicitly
named CSRF exemption: a one-click unsubscribe comes from a mail client
with no Origin and no Referer, the link already does the same thing as a
GET, and the thing actually guarding the row is 128 random bits. The
alternative to making that button work is the other button, marked spam.

**"How would I show this was done properly?"** The row could not have
answered. It knew somebody typed an address and that somebody later
clicked, with nothing in between. It now records the sequence -- what
they were shown and where they were, when the invitation was sent
(stamped after the mail server took it), when and from where it was
answered -- and the Email list screen says, in words, what each part of
it is for.

**"Can I remove somebody by hand?"** Yes, and it needed to exist and to
be distinguished from unsubscribing. An unsubscribe stops the mail and
keeps the row, which is what evidences that it stopped. Erasing takes
the person out of the site altogether, consent record included -- which
is what somebody asking to be forgotten is entitled to, and takes the
proof with it. The confirm dialog says exactly that before it happens.

`tools/signup_check.py` walks the whole path against a throwaway site
with the mail captured rather than sent, because testing this by hand
means really subscribing a real address through the owner's real mail
server. 26 checks. It caught the CSRF rejection above.

A block's markup IS its stored value, so none of this reaches a page
that already exists until the page is written again: a migration rebuilds
every stored sign-up through the block's own parser and builder, and the
16 shipped templates were rebuilt the same way. The renderer net moved by
exactly one block type in both views and nothing else.

## 2026-08-25 - An icon says what it is about to do

Two things about the icons that replaced the admin's buttons, both from
looking at them on a phone.

**"It is not always clear what these icons do."** True, and a tooltip is
not the answer: it only helps somebody who thinks to hover, and on a
phone there is no hover at all. So the sentence the icon replaced is not
gone -- it is asked. Every action names itself before it happens: "You
are about to delete the page "Contact" and everything on it. This cannot
be undone." OK, or Cancel.

That meant one implementation, because there were three. A native
`confirm()` spelled out in an `onsubmit` attribute (seven of those --
and native dialogs are refused outright in some embedded and preview
contexts, where the action then just looks dead), this codebase's own
`[data-confirm]` handler on a button, and `integrations.js`'s separate
`.cms-confirm-form` doing the same job on a form. They had drifted in
wording, in what Cancel did, and in whether they ran. `confirm.js` now
handles all three shapes -- a button submits its form, a link follows
its href, a form submits -- and `admin/base.html` loads it on every
admin screen, so a new action never has to remember to bring its own
dialog. Red is kept for what cannot be taken back; opening a page to
edit it asks in grey.

Also: **a column of symbols with nothing over it** leaves you guessing at
all of them at once. Both icon columns have a heading now -- "Home" and
"Action".

**"Technically the bakery home IS in use."** Every page on the site was
labelled "bakery template - not in use", and every one of them was
wrong. The first content edit on a site running a built-in takes a copy
of it -- "Bakery (your copy)" -- so the stock template is never quietly
modified. That copy took the look, the colours, the header and the
footer with it, and left behind the one line on each page recording
which template it arrived with. So the pages went on naming the
built-in, and the Dashboard, comparing that against the active
template, told the owner their entire site came from something they
were not using -- at the exact moment all of it was most in use.

Three parts to the fix. The fork now carries the origin across, because
the copy IS those pages. A one-time repair does the same for a site
forked before today, identified by what actually marks a fork rather
than by a guess: the active template is not a built-in, it is named
"<X> (your copy)", and X is a real built-in whose slug those pages
name. And the line itself is now shown **only when it is news** -- a
note under every page saying it came from the template in use says
nothing, since that is where pages normally come from. It appears when
a page came from somewhere else, and the row's tooltip answers the
question either way.

## 2026-08-25 - A row that was its own table

"There's a lot of disorder. Align everything uniform. Edit and delete in
the same row or the same column but not both."

Both true, and one cause behind them. `.simple-table` was `display:
block` so it could scroll, with `thead, tbody, tr { display: table;
width: 100% }` to put the rows back. That is a well-known trick and it
has a well-known cost: **a row that is its own table works out its own
column widths.** Nothing lined up with the row above it. A page with a
long name left less room, so its three icons became two and one; the next
row kept all three together. Some rows showed an L, some a line, and each
column started somewhere different.

A table's columns being shared between its rows is the entire reason to
use a table. So the BOX around it scrolls now -- `.table-scroll`, a class
this stylesheet already defined and nothing used -- and the table is a
table. All five admin tables are wrapped.

Two smaller things on top:

- **The action icons never wrap.** They stay on one line and the column
  takes exactly the width they need: `width: 1%` with `white-space:
  nowrap`, which is the old way of saying "as narrow as your content and
  not a pixel more". If the whole table then will not fit, the box
  scrolls -- which is what it is for.
- **Smaller circles on a phone**, 28px rather than 32, so three of them
  still fit beside the widest page name.

Measured at 375px afterwards: every column in both tables starts at
exactly one x across every row (pages 39 / 127 / 211 / 264, templates
39 / 171 / 232), every action group is one line of 28px, and nothing
scrolls sideways.

**Left unexplained, and said rather than buried**: the render check's
editing view grew 2130 bytes over this change and I did not trace it. The
visitor view is byte-identical, the figure is stable across runs, no
admin markup appears in a public page, and all 22 admin screens render --
so it is recorded and re-recorded rather than chased further.

## 2026-08-25 - The admin screens learn the editor's alphabet

The editor has said the same things the same way for a while: a pencil
edits, a red × removes, a tick is a state rather than a button. The admin
screens were the last place still spelling those out in words -- and a
word is about four times the width of the thing it names, which is why a
four-column table on a phone had buttons taller than the rows they sat
in.

**Pages.** The column is headed "Home" and the tick under it says which
one, so the word is not repeated in every row; a house icon makes a
different page the home page. Edit is a pencil, Delete a red ×. The row
went from 129px to **87px**, and the actions from three stacked lines to
one.

**Templates.** ▶ to use a look, ⤓ to take a copy away, ↻ to reload what it
ships, × to remove it. Four actions in the room four words used to need.

**Blogs are a tree**, which is what they are: a blog IS a set of posts,
and a list of blogs here with the posts on another screen made you hold
that relationship in your head. Each blog carries + to write a post, a
pencil to rename and a × to delete; each post under it carries a pencil
and a ×, and a draft says so. The pencil opens the rename with **no
script at all** -- a `<details>` whose `<summary>` is the button, so what
it reveals sits under the row it belongs to.

**The tooltip is not decoration here, it is the only text.** All 72 icon
controls on the Dashboard have one, and that is checked rather than
assumed. The rule this project already had -- every control gets a title
AND a hint, because the person using it may never have built a website --
becomes load-bearing the moment the label is a glyph.

## 2026-08-25 - The admin screens on a phone

"The blog admin section looks ugly" and "the buttons can be smaller in
mobile view so they fit better without bloating the view." Both were the
same underlying thing: controls sized for a desktop, in a column about
90px wide.

**The blog list.** It reused `.inline-form`, which is built for a settings
row and gives its input a 180px minimum -- so the Rename button beside the
name could never fit, wrapped to a line of its own, and stretched to full
width. Three stacked full-width buttons per blog, under a bullet. It has
its own layout now: name and Rename on one line, the address with the
post count and Delete beside it on the next. `min-width: 0` on the input
is the load-bearing part -- a flex item will not shrink below its content
width without it, which is what pushed everything onto new lines.

**The tables.** Three fixes, in order of how much room they gave back:

- `table-layout: fixed` divides the width equally, so a four-column table
  on a 375px screen gave every column the same 85px whatever was in it.
  Auto lets a column take what it needs; the table already scrolls inside
  its own box when the total will not fit.
- `code` breaks anywhere in this stylesheet, so that a webhook URL cannot
  set the page width. In a table cell that turned `/contact` into
  "/conta ct". It does not break there any more.
- Table buttons are 13px with tighter padding on a phone. A full-width
  primary action like "+ Add New Page" is meant to be large and is left
  alone.

**And two labels.** "Edit on Page" became **Edit**: the row is a page, so
the longer label repeated what the table already said, and in 85px it
broke across three lines and made a button taller than its own row. The
origin note I had just added went from "came with the bakery template" to
"bakery template". Both explanations moved to the tooltip, which is where
an explanation belongs.

Measured at 375px, before and after: every action button is now one line
and 44px tall (Edit was 68x53 across three), a page row is 112px rather
than 129, an address no longer breaks mid-word, and nothing scrolls
sideways.

## 2026-08-25 - The Dashboard says one thing in one place

Four complaints about one screen, and three of them were the same
complaint: it said things twice.

**"Pages from templates you are not using" is gone.** It listed pages that
were already listed in Your Pages, in a card of its own, with its own
Remove button and its own opinion about which pages count. What it knew
that was worth keeping was where a page came FROM, and that now sits on
the page's own row: *came with the bakery template*, and *— no longer the
one in use* when that is true. A page is deleted from the row that names
it, or from the page itself. One list, one place, one Delete.

**Blogs can be made and unmade.** The card listed them and opened them,
and the only way to CREATE one was to drop a Blog tool on a page and let
it make one for you -- a fine shortcut and a poor only route. There is an
Add, a Rename beside each name, and a Delete that says what it is about to
destroy ("and its 4 posts") rather than asking whether you are sure.

A blog IS a set of posts, so deleting one deletes them: a post with no
blog has no address, because its URL is built from the blog's slug.
Renaming deliberately leaves that slug alone, so every link to every post
keeps working -- which is why the field says so in its tooltip.

**"Active" was a column beside "Type", and on a narrow screen the badge
sat on top of the word next to it.** It is not a type, it is a state, and
it belongs with the name of the thing it is a state of. Three columns
instead of four, and the collision cannot happen.

**One mistake worth recording.** Cutting the stale-pages card, I cut from
its `{% if %}` to the `{% endif %}` before the next heading -- and the
Your Blogs card was sitting INSIDE that range, so it went too. Caught by
checking the rendered page rather than the diff: the add-a-blog form was
missing, which was the thing I had just added. **A range delete in a
template is only as good as your certainty about what is between the
ends.**

And a small honesty fix to the render check itself. The new "sign-ups will
be turned away" warning depends on whether the site can send email and has
a postal address, which made the check's output depend on the machine it
ran on -- two runs of an unchanged app disagreed. The fixture sets those
settings itself now: it is measuring the renderer, not the environment.

## 2026-08-25 - Shipping the templates with the changes actually in them

"Make sure all templates are updated correctly with the changes so they
are ready for shipping." They were not. **A block's markup IS its stored
value**, so every change to how a block is built reaches a template only
when the template is written again -- and three changes today had not
been:

- the sign-up button still wore `cms-buy-btn`, the Buy tool's own class
- `data-field` still sat on `<button>` in 16 files and on `<a>` in 28,
  so the words in those controls could not be typed into until the editor
  healed them on sight

Rebuilt with the app's own parser and builders rather than edited by hand:
`parse_block` reads the old shape, the builder writes the current one, 45
files across all sixteen templates. A fresh install now gets what the
editor would have produced.

**The safety check took three goes, and the first two were the
interesting ones.** Refusing to write a rebuild that loses something is
right; deciding what "loses" means is the hard part.

1. Comparing each value against the rebuilt HTML refused 11 blocks: a
   pricing block's features arrive newline-joined and leave as `<li>`
   items, so the joined string is never in the markup.
2. Comparing against the rebuilt TEXT refused them for a different
   reason: settings like `solid`, `/contact` or `horizontal` are
   attributes and never appear as words at all.
3. The honest test is a **round trip** -- parse the new markup back and it
   must say exactly what the old markup said. Zero refused, and it is not
   fooled by presentation.

**And the reported failure: "Sign-ups aren't working just now."** Email
WAS configured; what was missing was the postal address, which an email to
a list has to carry. The refusal is correct -- but it was only ever shown
to the VISITOR, who is the one person who can do nothing about it. The
Email sign-up tool now says so in the editor, names what is missing, and
links to the screen that fixes it. A visitor never sees that.

Verified by installing all sixteen templates fresh: 79 pages, 0 failures,
and zero occurrences of any of the five stale patterns.

## 2026-08-25 - Adding a row is a question for the panel, not the server

"Clicking + reloads the page." It did, and my own fix the hour before had
caused it: pressing + posted to the server, and I had made that response
re-render the page's regions so the panel would show its new row. That is
a correct way to get the right answer and a terrible way to add a box --
it throws away where you were.

**A line becomes content when something is written in it.** So + is a
question for the panel and nothing else: put an empty box under the line
whose + was pressed, with the caret in it, and tell the server nothing. It
learns with the first character typed, which already saves. Removing a
line IS a change to what is published, so - takes the row out and then
saves what is left.

The new row is **cloned from the one next to it** rather than written out
in JavaScript. This file has no business knowing what a contacts row looks
like -- that is the template's -- and a second copy of it here is exactly
the drift this project keeps undoing.

Two details that took a second attempt each. The caret: focusing the new
box inside the click handler does nothing, because the button takes focus
on mousedown, which happens afterwards -- it is deferred a tick now. And
the buttons carry their target in their own value (`add_2`, `del_2`), so
every row is renumbered after an insertion or a removal, or the next
press acts on the wrong line.

Verified in a browser, on the top row and the bottom row: the empty box
lands BELOW the line whose + was pressed, the page does not move, nothing
is published until something is typed, and after a reload a blank left in
the middle is still in the middle with the published lines skipping it.

**And three harness failures worth more than the fix**, all of them mine:

- **The placement check wiped a container that was being used for
  something else.** It deletes every section between placements, and it
  was pointed at the same site a browser had open -- which then went on
  posting to sections that no longer existed. It has its own DATA_DIR now.
  `render_check.py` records this exact lesson at the top of its file; I
  read it, and wrote the same bug anyway.
- **Then it signed in to the wrong site.** With its own database it kept
  reading the container's first-run password file, so the password change
  failed, every admin POST redirected to /admin/account, and every create
  was refused -- reported as "does not render" for things that render
  perfectly well.
- **And a `NameError` in the harness was reported as six broken
  containers.** Rewriting one function deleted a regex the next one used;
  the bare `except` turned that into "does not render" for 180
  combinations. It prints the traceback now and says "the harness raised"
  rather than blaming the app.

Same shape each time: **the harness is not the app, and when it disagrees
with the app the harness is usually wrong.** A uniform column of failures
is a statement about the measurement.

## 2026-08-25 - Divisions, side rails, and a helper that called itself

Two more things asked of the same requirement, and both found real bugs.

**One or many cell divisions, in every position, body and side.** The
placement check now covers a Columns block of one, three and six cells
with the tool in the first, a middle and the LAST of them; a cell split
into four rows with the tool in the first and the last; and the same
shapes inside the sidebar. 570 combinations. The ends matter more than
the middle -- first and last are where an off-by-one shows.

**Twenty-seven give-up paths answered 500 instead of redirecting.** Every
column route ends with the same line when it cannot find what it was
asked for:

    return redirect(url_for("admin.page_edit", page_id=section["page_id"]))

A zone section belongs to a template and has no page_id, and `url_for`
with `page_id=None` does not build a URL, it raises. So every one of those
paths crashed -- but only ever for a tool standing in a side rail, a
header or a footer, which is why it had never been seen. `_redirect_next`
had already worked this out and falls back to the dashboard; they all go
through one `_section_home()` now.

**And the fix broke three columns of the matrix**, which is the part worth
keeping. The sweep that replaced those twenty-seven lines also replaced
the line inside the helper it had just written, so `_section_home` called
itself: `RecursionError`, and every row placement in the body started
failing. **A search-and-replace that includes the thing it is creating
will rewrite it too.** The matrix caught it immediately, which is the
argument for having built the matrix.

**Contacts: + adds a row, typing publishes.** Reported as "the +/- is
supposed to allow a new row not add the content; content should be added
real time". The +/- semantics were already right -- an empty row is kept
in the form and never written to the page, with `data-rows` and
`data-blanks` on the wrapper remembering where the gaps are, because the
block IS the storage. What was wrong was that none of it showed:

- **A Contacts SECTION had no `cms-block-host`.** The cell version had
  one; the section version fell through to the branch that renders an
  editable body, so the editor had nowhere to put the rebuilt block and
  nothing changed until a reload. It was also contenteditable over markup
  the tool derives and overwrites. One missing name in a list of eleven.
- **Pressing + changed the form, and only the block was being swapped.**
  So the new row did not appear until a reload either. A +/- now
  re-renders the page's regions (`cmsRefreshSite`), because the panel is
  server-rendered and the server is what has to render it again. Typing
  still takes the fast path.

Proved in a browser, not by reading the code: typing published the line
with no reload; + gave a second empty row while the published count
stayed at one; typing in it published the second; and - removed the row it
sits on and republished the rest.

## 2026-08-25 - Every tool, in every place a tool can be put

Stated as a requirement: a tool must work wherever it is placed. Sections
and tools get added, removed and moved into whatever space is free, so
none of them may depend on being in one particular slot.

That is a claim about 180 things, so it is measured now rather than
believed: `tools/placement_check.py` puts all 30 tools through all six
containers -- a section of its own, a cell of a Columns block, a row
inside one of those cells, and the header, sidebar and footer zones -- and
asks three questions of each pair. Does the tool's block render there.
Does the editor give it a tool header, so it can be moved or removed. And
does every form the editor rendered for it actually round-trip. Rendering
somewhere you cannot save is not working there.

**270 of 270 pass** -- and the footer is asked four ways rather than one,
because a footer is not a fixed shape. It can be empty, with the tool's
own section the first thing in it; or it can have any of the three
starting layouts applied first, with the tool dropped into a cell of what
that layout built, which is how the Contacts tool actually lives there.
All four behave the same.

One thing noticed while checking the presets really applied, and left
alone rather than quietly changed: applied by hand, all three build **two**
cells. The Columns preset's own description promises three -- "menu links,
contact & social icons, a closing note" -- and the third only appears when
a template supplies contact details, so the manual route produces
something the description does not describe. The code says why (there is
no real contact information to seed at that moment), but the app now has
the business's name and address on file and a Contacts tool to hold them,
so the honest fix would be to seed an empty one. Worth doing; not part of
this.

One real defect was found on the way:

**Collapsing a Columns section crashed.** `section_divide` with a count of
1 merges the cells back down, and took `cells[0]` to be a string. A cell
is a string when it holds words and a **dict** when it holds a tool, so
dividing a section back down with anything but text in its first cell
wrote a dict into a TEXT column and answered 500: `type 'dict' is not
supported`. That is the requirement failing exactly as stated -- a tool
that cannot survive its container being changed. It keeps the tool now,
and a cell that is itself split into rows keeps its rows instead of
throwing them away.

**Three false alarms, each of which looked like a catastrophe**, and all
three are written into the check's own docstring because the next person
will hit them:

- Marking each tool by injecting a span into its starter content reported
  Image, Media Player and File as rendering nowhere. Their content is a
  URL, not markup, so the marker was never rendered. 136 of 180 "broken".
- Posting to `/columns/N/split-rows` 404s -- the route is `/columns/N/rows`
  -- so every row placement silently did nothing and all 30 tools looked
  unmanageable in a row.
- Holding the active template's id in a variable reported all three ZONES
  broken for all 30 tools. The first content edit forks the builtin and
  makes the copy active, so the id goes stale and the zone sections were
  created on a template nobody renders.

The tell each time was the shape of the failure: **thirty tools do not
break in the same way on the same day.** A column of identical failures is
a statement about the harness, not the app. Each one had to be chased to
its cause before the number underneath it meant anything.

## 2026-08-25 - Two copies of one template, and a save with nowhere to land

"Couldn't save — check your connection", on a Contacts tool that looked
fine. The connection was fine. The tool was pointing at a section that no
longer belonged to the active template.

**How the site got there.** `fork_active_builtin` gives a site its own
copy of the builtin it is using, the first time content is edited. It read
"the active template is a builtin", then did the work. Gunicorn runs
several workers and the editor fires several requests at once, so two of
them read that in the same instant and both forked: this install ended up
with `bakery-your-copy` AND `bakery-your-copy-2`, and the second one had a
header but **no footer**. The page somebody had open was still rendered
from the first copy's footer, so saving posted to a section id the active
template did not own -- the route redirected, the editor was waiting for
JSON, and `res.json()` threw straight into the "check your connection"
branch.

**The third instance of the same mistake today**, which is what makes it
worth an entry rather than a line. A SELECT that decides, followed by
writes that assume the decision still holds:

- `seed_admin` printed a password that opened nothing.
- `_restore_opening_hours` added the section twice, once per worker.
- and this.

All three are one UPDATE or INSERT away from being safe, because a single
statement's `rowcount` is the only answer that arrives after the write
rather than before it. The fork now claims itself:

    UPDATE templates SET is_active = 0
     WHERE id = ? AND is_active = 1 AND is_builtin = 1

One winner, and the loser leaves. If the copy then fails the builtin is
put back, so a failed fork cannot leave a site with nothing active.
Verified with three threads on one database: one fork, one copy, one
active template, and the copy carrying its header AND its footer with the
contacts in it.

**And a mistake of my own, worth recording because of where it landed.**
Diagnosing this, I posted to the live site's contact-update route to see
what it answered -- and that route does not just answer, it SAVES. It
wrote a one-row Contacts block over a three-row one. Restored from the
template, but the lesson is the shape: a route named `*_update` is not a
diagnostic, and a running site somebody is using is not a test fixture.
There were two throwaway containers up at the time.

## 2026-08-25 - Does it survive being turned off?

Asked directly, so it was answered by doing it rather than by reading the
compose file.

**The old subscribers are gone, and the migration stopped confirming
anyone.** With no real data to protect, the strict reading is the right
one: a row that predates double opt-in has no confirmation to point at, so
it stays unconfirmed. The rule is about being able to SHOW that somebody
asked, not about whether they probably did. Nothing is deleted and nothing
is silent -- such a row appears on the Subscribers screen as waiting to
confirm, and a send skips it. The version that marked them confirmed
because they were live yesterday was written first and taken back out:
that decision belongs to the owner of a list, deliberately, not to an
upgrade acting on their behalf.

**Persistence, tested on the real deployment.** Fingerprinted the live
site, ran `docker compose down` -- the container destroyed outright, not
restarted -- and brought it back:

    pages 5, sections 59, templates 17, settings 42, users 1
    uploads 46 files, themes 26 directories
    the encryption key and the session key both still there

All identical afterwards. Everything that matters sits under one of three
bind mounts (`./data`, `./uploads`, `./themes`), including the things it
would be easy to miss: the database, the session key, the key that opens
the encrypted settings, and `private_downloads/`, where paid files live
outside the served tree.

**And the test harness failed in a way worth writing down.** The first
attempt used a throwaway container with bind mounts under the Windows temp
directory, and reported half the data lost. It had not been lost -- the
mount silently did not work, and because the Dockerfile declares
`VOLUME ["/app/data", ...]`, **Docker quietly substituted an anonymous
volume**. The container wrote happily, the host directory stayed empty,
and a fresh container got a fresh volume.

That is exactly how somebody loses a site without ever seeing an error:
point a mount at a path Docker is not sharing, and the app keeps working,
keeps saving, and keeps nothing. The tell is that the app announces a
first run -- a generated admin password -- on a site that should have had
one months ago. Worth knowing before it happens rather than after.

**Opening hours are back**, as a Text section above the contact form,
carrying their original wording read back out of git. They are not a
contact type and never were: they are two lines of text, so they are in
the tool that holds text. The address stays in the footer's Contacts tool
where it belongs.

## 2026-08-25 - Nobody is on the list until they answer

Reported with a screenshot: the tick box was still there. It was, and the
reason is worth more than the fix.

**The migration ran and did nothing.** It looked for
`<input type="checkbox"`, which is what the builder writes -- and not what
a page stores. Every save goes through BeautifulSoup, which alphabetises
attributes and closes empty tags, so what is actually on disk reads
`<input name="consent" required="" type="checkbox" value="1"/>`. The regex
could not match it, the migration reported nothing to do, and the box
stayed exactly where it was. **Markup that has been through a parser has
to be matched with one**, which is what it does now.

Then the substantial part: **double opt-in, because Switzerland requires
that somebody sent advertising actually asked for it.**

- Signing up writes the address down and sends **one** mail, with a link.
- Nothing else is ever sent until that link is followed. `listing()` grew
  a `confirmed_only` flag and a send reads it -- an address that never
  answers stays on the table, visible to the owner, marked "waiting to
  confirm", and is never written to again. That is the not-confirmed list.
- Following the link puts them on it. Idempotent, because a link followed
  twice, or fetched by a mail client before a person sees it, must not
  read as a failure to somebody who did what was asked.
- Every mail after that carries an unsubscribe link, which
  `send_to_list` already did -- one message per person precisely so each
  carries its own.
- Coming back after unsubscribing is a fresh consent, so it confirms from
  scratch. Typing an address in twice while it is still pending re-sends
  the same invitation rather than making a second row, because the usual
  reason for doing that is that the first mail did not arrive.

**Three things that had to be built around it.**

*The sign-up had no voice.* `/subscribe` redirected with `?subscribed=1`
and **nothing anywhere displayed it** -- somebody typed their address, the
page reloaded, and that was the entire response. Thin before, impossible
now: the one thing a person must be told is to go and look in their inbox.
The page says what happened.

*It refuses rather than pretends.* Without a mail server, or without a
postal address on file, there is no way to confirm -- so nothing is
written down at all, the visitor is told plainly, and the owner gets it in
the log. Half-subscribing somebody who can never be confirmed is worse
than declining.

*The sender's identity needed a home somebody would find.* An email to a
list has to name who sent it and give a real address; that was already on
file from the legal pages and already refused-if-missing. It is now
editable on the Email settings screen too -- **the same two settings, not
a copy**, because one install is one business and its details are asked
for once. Verified: saved on one screen, read on the other.

Verified as a flow rather than as functions: no mail configured leaves
nothing on the list, a sign-up sends exactly one invitation carrying an
absolute link and the sender's name and address, a send would reach nobody
until the link is followed and exactly one person after, following it
twice is still success, and unsubscribing empties the list again while
leaving the pending address untouched and unmailed.

## 2026-08-25 - Ten contact blocks that were only dressed as the tool

Three reports in one message, and the middle one was the interesting one.

**The tick box was still there.** It was: the previous change stopped
BUILDING one, and left every page already saved with the old markup alone
-- deliberately, and wrongly, because a site that has the box keeps asking
for it forever. There is a migration now. The wording stays as a line,
which is the part that matters: people have to be told what they are
agreeing to, and it is stored with each row as it was worded at the time.

**The contact page had two Contact Info tools, and the one in the body was
a fake.** Ten templates shipped a page whose body held:

    <div class="cms-contact-tool"><p>Flour &amp; Salt, 3 Lindenweg</p>
    <p>Wednesday to Sunday, 7 till sold out</p>
    <p>hello@flourandsalt.example</p></div>

A div wearing the tool's own class with three hand-written paragraphs
inside it. It reported itself as "Contact Info" in the editor and offered
the Contacts panel -- and would have destroyed itself on first use, since
reading rows out of it returns none and saving writes those none back. No
icons, no links, an email that could not be clicked. **Exactly what
CLAUDE.md warns against in as many words**: markup hand-built to look like
a tool instead of composed from one.

Gone from the templates, and a migration removes it from sites that have
it -- matched on the shape, so a block holding real `cms-contact-detail`
rows is the genuine tool and is left alone.

**Then the address had to land somewhere**, which is the third request.
The tool now understands a postal address, read from what was typed like
everything else in it -- there is no type dropdown to argue with, by
design. A comma or a line break is what separates "Unit 4, St. Mary's
Road" from "flourandsalt.example", and no email, phone or web address
needs either.

That test had to be asked BEFORE the existing "contains a dot, so it is a
domain" rule, **which was a live bug**: any address with a full stop in it
became a link to `https://Unit 4, St. Mary's Road`. An address is a place,
not a page; it gets the pin without being asked, and keeps any line breaks
typed into it.

Each template's address moved into its footer's real Contacts tool, read
back out of git rather than retyped so nothing is invented.

**And that turned up a fourth thing nobody reported.** Two of the ten use
`footer_layout: simple`, and simple was the one preset that never rendered
`footer_contact` at all -- so those two addresses would have landed
nowhere. Worse, it was already true for **four** templates: clinic, cv,
fitness and self-help each declare an email, a phone or a website in their
manifest that their footer has never shown. The manifest said one thing
and the site showed another. Simple means the fewest cells, not "discard
the details this template shipped", so it includes them now.

Verified across all sixteen: every detail each manifest declares appears
in its footer, addresses pinned and not linkified, 79 pages, 0 failures,
no hand-written contact block left anywhere.

**Still lost, and worth saying rather than hiding**: those ten blocks also
carried opening hours ("Wednesday to Sunday, 7 till sold out"). Hours are
not a contact type and the footer tool has nowhere to put them, so they
went with the block. If they should come back it is a decision about what
the tool holds, not a bug to patch quietly.

## 2026-08-25 - A tick box asking for the thing the button already did

"What is the check box for, the user is already signing up with the
button?" Nothing, on this form. It is gone.

The Email sign-up rendered a **required** tick box reading "Yes, email me
occasional updates" -- under a heading about updates, on a form whose only
purpose is subscribing, next to a button that says Sign up. The same act,
demanded twice, with the second one able to fail.

What consent actually requires is that the person is **told** what they
are agreeing to and that it can be **evidenced** afterwards. Both were
already satisfied by something else on that form: the wording is shown,
and a hidden `consent_text` stores the exact words they were shown with
their row -- deliberately, because the block will be reworded later and
the promise made to somebody last spring is the one that counts. The box
added a second gate, not a second protection.

Checked before changing it: **nothing else in this app posts to
`/subscribe`.** There is no case here of an address collected for
something else with marketing bundled alongside -- which IS the case that
needs an unbundled tick box, and if one is ever built it needs its own,
not this one back. That is written into the code beside the change so the
reasoning survives the next reading.

So the line stays as a line and the box goes. The route follows: sending
the form is the consent. It still honours a box that a page saved before
today sends -- absent means the new markup, present-and-false means
somebody posted an old form around its own `required` attribute -- which
is the difference between removing a control and ignoring one.

    new form, no consent field    -> subscribed=1
    old form, box ticked          -> subscribed=1
    old form, box NOT ticked      -> subscribed=consent
    stored with each: the exact wording shown

The CSS followed too: that rule was laying a tick box out beside text with
flex and a gap, and is now one paragraph with a margin.

## 2026-08-25 - A button label nobody could type into, and a hint that promised they could

Two reports, one cause. "The intro text is still wrong and the submit
button text is not editable."

The panel above every declared block says: *"Everything you can see on the
page is edited on the page -- click any heading, price or line of text and
type."* On an Email sign-up it was wrong twice. "Price" is a pricing
table's word and means nothing there. And the promise itself was false,
because the sign-up button's label could not be typed into at all.

**Why it could not be.** The editor makes every `[data-field]` inside a
block `contenteditable`, and its own comment says "each editable is a leaf
holding text". Three blocks broke that rule -- newsletter put `data-field`
on a `<button>`, and Pricing and Call-to-action put it on an `<a>`. A
browser will not place a caret inside a control, however editable the
attribute says it is.

Fixing it properly took **four** things, and each one looked like the
whole fix until it was tested:

1. **The words moved into a `<span data-field>` inside the control.**
   Necessary, not sufficient.
2. **`parse_block` had to read the two facts separately.** It read
   `data-href-field` off the same element as `data-field`, so moving the
   text into a span would have silently stopped a link's target being read
   back. It scans for each independently now, which reads old markup and
   new.
3. **The control had to stop swallowing the click.** `pointer-events:
   none` on a block's buttons and links while editing, `auto` on the
   elements holding words -- otherwise the click never reaches the span.
4. **And the click's DEFAULT action had to be cancelled.** This was the
   one that kept it broken after everything above. `pointer-events` only
   governs hit-testing; the event still bubbles THROUGH the button, whose
   default action is to submit its form. The sign-up form has a required
   email box, so the browser failed validation and moved focus to it --
   the caret was placed and then immediately taken away, which is
   indistinguishable from the label being uneditable.

The editor also heals pages saved before this: a `[data-field]` found on a
button or a link gets its words moved into a span at load, so an existing
newsletter is editable immediately and stores the corrected markup the
next time it saves. Verified on both: one block built today and one
inserted in the old shape.

Proof was a real click and real keystrokes, not a rendered attribute: the
label reads "Sign now up" afterwards, because the caret landed **where it
was clicked** rather than at the end. Both saved; the legacy one healed to
the span form in the database.

And the hint now says "click any heading, line of text or button label and
type", which is true of every block it appears under.

**The lesson**: a promise in the interface is a test. That sentence had
been sitting above a control that could not do what it said, and the
sentence is how it was found.

## 2026-08-25 - An Email sign-up that thought it was a Buy Button

Reported as a question: "email sign up contains buy now and product,
that's surely not correct?" It was not.

The Email sign-up's submit button was rendered with `class="cms-buy-btn"`
-- the Buy tool's own class. From there, three separate things went wrong,
and only the third was visible:

1. **Its styling belonged to another tool.** Any change to how Buy looks
   silently restyled a newsletter's Sign up button.
2. **The label test was a substring away from lying.** The marker table
   checks `"cms-buy" in content`, and `cms-buy-btn` contains it. An Email
   sign-up escaped being labelled "Buy Button" only because the block
   markers happen to be tested FIRST. Ordering, not correctness.
3. **The detection test had no such luck.** `if "cms-buy" in d["content"]:
   d["is_buy_button"] = True` -- same substring, no ordering to save it.
   So an Email sign-up WAS a Buy Button as far as the editor was
   concerned, and was handed the Buy Button's panel: a Stripe price id, a
   "Buy now" label, a product name and a price. Which is exactly what was
   reported.

The class was doing two jobs -- naming a tool and describing a look -- and
the app had been using it as the second while the code tested it as the
first. Split:

- `cms-action-btn` is the look: the site's primary action button,
  wherever it appears. Named for what it is rather than for the first
  tool that needed it.
- `cms-buy-btn` stays the Buy Button's identity, which
  `buy_button_settings` reads back. Its button carries both.
- Eight more buttons across the templates were wearing the buy class for
  its looks alone -- Checkout, Add to basket, Download now, Confirm
  booking, and "Yes, cancel it". None of them is a purchase; the last is
  the opposite of one. They take the shared name now.
- Both `"cms-buy"` tests became `"cms-buy-style-"`, which
  `build_buy_button` writes and nothing else does. **That is the part
  that fixes existing sites**: changing the class only helps blocks built
  from now on, and every page already saved still holds `cms-buy-btn`.
- `.cms-buy-btn` stays in the stylesheet's selector for the same reason.

Verified on all three: an Email sign-up saved before today, one built now,
and a real Buy Button. The first two report `is_buy_button=False` and
label as "Email sign-up"; the third is unchanged and still reads its price
id back.

**How it was nearly missed.** The render check moved 2130 bytes in the
editing view with no per-block hash changing, and the first instinct was
to treat that as noise from a class rename. It was the newsletter's panel
changing from the Buy Button's five fields to its own five -- the bug
being fixed, showing up as a number. Chasing an unexplained diff instead
of waving it through is what turned "the class is wrong" into "and here is
what it was doing".

## 2026-08-25 - The last three tools that were two tools

Finishing what the measurement found. Each was one tool behaving as two,
and each is one definition now.

**Media Player.** A section could set the Player size; a cell could not --
and the reason the control was missing is the same reason it would not
have worked: a cell rendered its player into a bare `<div class="cms-column-body">`
rather than the `block block-media` wrapper that carries the size class,
so there was nothing for the control to act on. One `media_controls()` and
one `media_tool()` now, called from both. The cell route already accepted
`width`, so nothing new was needed behind it.

**HTML / Embed.** The section had a `</>` button opening a raw-code
editor. In a column there was none -- so the one tool whose entire purpose
is holding code could not have its code edited, in half the places it can
be put. Two small macros (`embed_code_button`, `embed_code_editor`) called
from both, and the handler now closes on `.cms-column, .cms-section`
rather than `.cms-section`. That detail matters: scoped to the section, a
click in the second cell would have opened the FIRST cell's editor.

**Basket.** Worst of the three, because it was not a difference in
controls -- the cell renderer did not recognise a Basket at all. It fell
through to the catch-all and got a bold/italic ribbon, as though the
basket were words somebody had typed. It has its three settings now (how
it looks, where it sits, hide when empty) over a
`section_column_basket_update` route shaped like every other column-scoped
update. That is a 34th route pair, which is the wrong direction for
Phase 3 -- worth noting rather than hiding, since the alternative was
leaving a tool that cannot be configured where it stands.

**A mistake worth keeping.** Adding `cms-html-preview` to the cell, I then
gated it on `editing`, reasoning that a class named "preview" is the
editor's business and CLAUDE.md says editor markup does not ship. Checked
before committing: `site-base.css` styles `.cms-html-preview` for
visitors -- link colours, and `overflow-x: auto` on one holding a table.
It is not editor markup; it marks "this element holds tool-rendered
HTML". Gating it would have taken link styling and table scrolling away
from every embed in a column. **The name suggested editor; the stylesheet
said site.** Reverted, and both views carry it, as the section already
did.

Where that leaves it: **28 of 29 tools offer identical controls in both
places.** The one line remaining is the Media Player showing the same
macro in two states -- the section instance is a YouTube one and the cell
instance a video one -- confirmed directly: both offer Player size with
the same four options, and both now render the same `block block-media`
wrapper.

Verified by using them, not just rendering them: the Basket's three
settings save from a cell and read back (style/align/hide), Player size
saves as `large` from a cell, and an Embed cell carries the `</>` button,
the textarea, Save HTML and the preview it swaps against, posting to its
own column route. All 16 templates, 79 pages, visitor view: 0 failures, 0
leaking editor markup.

## 2026-08-25 - Measuring "seventeen to go" found three

The backlog said one renderer per tool was "roughly seventeen to go".
That number was an estimate nobody had checked. Checking it changed the
job.

Built the comparison off `render_check`'s scratch site, which already
holds every tool once as its own section and once as a cell, and asked per
tool: what controls does each rendering actually offer? Scoped to the
tool's own panel on purpose -- a section carries Move up, Section width
and Content height, a cell carries Remove this tool and Number of rows,
and those belong to the CONTAINER. Differing there is correct.

**25 of 26 tools already offered identical controls in both places.** The
work done on Text and Image, plus everything the block system already
shares, had got further than the note recording it.

Two false starts in the measurement, both worth the warning. Scoping to
`.cms-section` swept up the whole page and reported Text as having 672
controls a cell lacked. Then excluding anything inside `.block` -- meaning
to drop a Contact Form's own name/email/message, which are content --
inverted the result and reported all 26 as section-only, because **in a
cell the tool panel lives INSIDE the block.** Naming the chrome
containers is symmetric; naming the content was not. A filter that is
wrong in one direction quietly deletes the evidence.

**And the naming was the real find.** A section takes its label from one
computed `display_label`; a cell had the name typed by hand into each of
twenty-two branches of `page.html`. Two had drifted, so the same tool
introduced itself differently depending on where it stood: "HTML / Embed"
as a section and "Embed" as a cell, "Media Player (Audio / Video /
YouTube)" against "Media Player". Nobody chose that; it is what
twenty-two literals do over time.

All twenty-two now use the same computation the section uses. It
reproduces every previous answer including the dynamic one -- the marker
table already distinguishes Menu (Dropdown) / Menu (Buttons) / Menu
exactly as the hand-written `menu_label` did. The render check moved by
36 bytes in the editing view and nothing in the visitor view, which is
precisely the two longer labels: +7 and +29.

**Unifying the names earned the rest of the answer**, because two tools
were only comparable once they answered to one name. What is actually
left is three:

- **Basket.** As a section it has three settings (hide when empty, how it
  looks, where it sits in the row). As a cell it has none of them and gets
  a text toolbar instead -- the cell renderer does not recognise a Basket
  at all and falls through to treating it as words.
- **Media Player.** Each side has something the other lacks: the section
  has Player size and a YouTube link box, the cell has Upload audio or
  video. Neither is complete.
- **HTML / Embed.** The section can Edit raw HTML/script. In a column you
  cannot edit the embed's code at all.

Three, not seventeen -- and each is a specific missing control rather than
a vague duplication.

## 2026-08-25 - A guard that had been reading a folder that no longer exists

Went to fix a small recorded bug and found a bigger one underneath it.

**The small one.** `_apply_pack_identity()` gives the site a template's
name, guarded by "only while the current name is still somebody else's
demo". The guard tested the TITLE; the write covered title AND tagline. So
an owner who had typed a tagline while the title was still "My Site" lost
it the next time any template was activated -- their name protected, the
line underneath it not. Each field is judged on itself now.

**The one underneath.** The guard builds its set of "names that are
nobody's" by reading every builtin's manifest, and it globbed
`app/data/templates/*/manifest.json` -- the AUTHORING sources. Those are
deleted from the runtime image by the packager stage, because templates
ship as zips now. **The glob matched nothing on every real install**, so
the set held only the three hardcoded strings, and the entire "another
template's demo name" half of the guard had been dead since packaging
changed.

What that cost, in the words of the function's own docstring: "leaving a
coffee roaster's name across a consulting firm's pages is the first thing
anyone notices." Activate the bakery, then the clinic, and the site stayed
called Flour & Salt -- because "Flour & Salt" was no longer recognised as
a demo name, so it was treated as something a person had typed.

It reads `static/themes/<slug>/manifest.json` for every row in
`templates` now, which is where an installed package actually unpacks to.
That is also strictly better than the glob ever was: it covers templates
somebody imported, which the source folder never contained.

Verified as four cases rather than one, which is what turned the small bug
into the real one -- the fourth ("another template's demo tagline is
replaced, not mistaken for the owner's") was the one that failed, and it
failed for a reason that had nothing to do with taglines:

    placeholder title replaced, owner's tagline kept     PASS
    a bakery's name does NOT survive onto a clinic       PASS
    an owner's own name and tagline both survive         PASS
    another template's demo tagline is replaced          PASS

**The lesson worth keeping**: when a feature moves house -- and shipping
templates as zips moved a whole tree out of the runtime image -- the
things that READ from the old address fail silently, because a glob that
matches nothing is not an error. Nothing threw. It just quietly stopped
protecting anything.

**So the obvious next question: what else was reading that address?** Two
more, both in `db.py`, both with the same shape -- compute a path into
`data/templates`, `if not os.path.isdir(...): return`.

- `_backfill_page_origins()` works out which template a page came from by
  fingerprinting its first section against what each package ships, and
  fills in `source_template`. That is what lets the Dashboard offer to
  remove "pages left behind by other templates". Dead, so a site upgrading
  from before that column existed never got its pages attributed and the
  offer never appeared.
- `_template_pictures_live_in_their_package()` rewrites picture URLs from
  the old shared `/static/img/templates/` folder into each template's own.
  Its docstring: "without this an existing site comes back from an upgrade
  with every template picture broken." Dead, so it would have.

Both now go through one helper, `_installed_package_dirs()`, reading
`static/themes/<slug>/` -- which carries the same `manifest.json`,
`pages/` and `media/` the source tree did, and covers imported templates
as well. It sees 16 packages where the old path saw none. Boot order is
noted in its docstring: `init_db` runs before `_seed` installs the
packages, so on the very first boot of a brand new install it returns
nothing -- harmless, since both callers exist to repair data from older
versions and a new install has none.

Proved rather than assumed: wiped `source_template` on a live bakery site,
ran the backfill, and all four pages recovered their attribution. Under
the old path it returned without looking at anything.

## 2026-08-25 - A setup wizard (specified; BUILT since)

**Built** -- `app/routes/admin/wizard.py`, six steps, and the "New here?"
banner that offers it. The specification below is kept because it is the
reasoning, not the record.

The one flow this app does not have: somebody who has just installed it,
looking at a bakery's demo content, with no idea that the palette, the
fonts, the layout, Stripe and the site address are all things they are
allowed to touch. Every one of those already works. Nothing introduces
them.

**What it does.** Walks a new owner from "I picked a template" to "this is
my website", one decision at a time, and each step says plainly: leave it
as it is, choose from the examples, or have AI write something new. The
point is as much the introduction as the configuration -- an owner who
finishes should know the Tools panel exists, know the Colors panel exists,
and know which integrations they have not set up.

**Where it starts.** Two named in the request, and the one that matters
most is not among them:

- A button under Templates. Always there, always re-runnable -- somebody
  changing template a year later wants the same walk-through.
- When somebody first edits a template: "Use this template for your
  website?" **This must be the same moment as the auto-fork, not a second
  one.** The first content edit of a builtin already forks it to a user
  template (see the 2026-08-25 entry). That is exactly when the question
  is worth asking, and asking it twice, or at a slightly different moment,
  makes two events out of one.
- Not named, and probably the real entry point: **the first admin login on
  a fresh install.** The Dashboard already knows it is one --
  `using_generated_password`, a site address that is not set. If the
  wizard is worth having at all it is worth offering here, before the
  owner has done anything they would need undone.

However it starts, it opens with the choice preselected from how it
started: entering from a template's own tile means that template is
already chosen.

**What it collects.** The request named the site name, the template
options, and keys for AI, Stripe and Cal.com. The gaps, in the order they
cost the most:

- **The site address.** `services/site.py` is the single authority for
  every URL that leaves this app: Stripe return and webhook addresses,
  every link in an email, the picture Stripe shows on its payment page.
  Unset, all of those are built from whatever host the admin happened to
  be typing, which is usually localhost. A wizard that sets up Stripe and
  not this has set up a Stripe that cannot come back.
- **Email sending.** Contact forms and newsletters are dead without it,
  and it is the integration a small site is most likely to actually need
  -- ahead of Stripe and Cal.com both.
- **The owner own details** -- business name, postal address, contact
  email. Three fields the wizard is asking for anyway, and exactly what
  `services/legal.py` writes the legal pages from. A newsletter is refused
  without a postal address. Collect them once here and two features that
  currently need a separate errand come free.
- **Palette and fonts.** Every template has a customizable palette now,
  real or `DEFAULT_PALETTE`, and `COLOR_PRESETS` exist. "Keep the
  template's / pick a preset / let AI choose" is the same three-way choice
  as every other step.
- **Favicon and logo.** Cheap, visible, and the Dashboard already has an
  AI generator for the favicon.

**Copy everything / just the look / show me my options.** The first two
already exist and are already worded: `template-panel.js` offers exactly
"Take everything" and "Just the look", over routes that already work
(forced and un-forced activation). **The wizard uses those, not a fourth
path.**

The third is the styling: layouts, colours, fonts. It does not apply
anything -- it drops into the wizard steps that cover how the site LOOKS,
with the template's own values preselected, so somebody can see what they
are choosing between before committing to it. "Take everything" and "just
the look" are both answers to "shall I apply this?"; this one declines to
answer yet and goes and shows you. It is the browse-before-you-commit
path, and it is what makes the prompt an introduction rather than a
gate.

Everything behind it already exists: `COLOR_PRESETS` and each template's
own palette, `FONT_PAIRINGS` and `GOOGLE_FONT_CHOICES`, the nav/page/
footer layout presets, and Corners/Depth. The Colors and Style panels are
those same options; the wizard is a guided path through them, not a second
copy of them.

(Separately, and NOT this: a preview of what content is about to be
replaced. Worth having, since "take everything" replaces pages that share
a name, and nothing new would have to be computed -- every package ships
an `install.json` from `package_inventory()` listing every page, its
section count and every picture, and `pack_content_conflicts()` already
works out the collisions. But it is a different feature from the styling
walk-through and should not be folded into it.)

**Rules it does not get to break.**

- **No AI-generated content unless the owner asks for it, in that step,
  and sees it before it lands.** AI is never the default and never the
  quiet fallback. Every generated option is shown, and accepted, rejected
  or regenerated -- not applied and then discovered. If no AI key is set
  the option is visibly unavailable with a path to add one, never a step
  that fails when pressed.
- **It must be abandonable.** Somebody who leaves at step four has a site
  in a coherent state and a wizard that remembers where they were (see
  Decided, below). Snapshot before it starts -- "Save current site as a
  new template" is this project's undo, and it is one call.
- **A fresh site and an established one are different.** On a fresh
  install nothing is at risk and the wizard can be bold; on a site with
  real content every destructive step needs the conflict view above. The
  wizard should know which one it is standing in.
- **Novice framing, hardest here.** This is the most novice-facing surface
  in the app, so CLAUDE.md rule binds hardest: a tooltip AND a hint on
  every control, plain quick-select controls, never a raw HTML box.
- **It is not a page type and not a tool.** It is an admin flow, and must
  not add a `wizard` page type or a special page (see "Features are tools,
  never page types").
- **It has to work on a phone.** 375px, which is where this app is
  actually being driven.
- **Structure**: `app/services/wizard.py` for the step definitions and the
  state, thin routes, the step copy in templates rather than Python
  strings, no inline script. The wizard orchestrates routes that already
  exist -- it should add almost no new behaviour, only a path through the
  behaviour there is. If a step needs a new route, that is a signal the
  step is doing something the app cannot already do.
- **Secrets**: keys go through `crypto.py` encrypted, are never echoed
  back into a field, and the app keeps working with none of them set.

**One install is one website, and the details are the site's.** This is
the rule the rest of the wizard hangs off. However many templates get
tried on, there is only ever one site here, so the name, the business
details, the address and the contact are captured once and are then the
single source of truth for everything in the app that needs them. The
wizard sets them; the Dashboard manages the same values afterwards;
reopening the wizard shows the same values, not a second copy. **And
loading a template or its content never changes them.** A template brings
a look and some pages. It does not bring an identity.

Three things in the code bear on that, and two of them are work:

- **The identity already lives in two places.** `site_title` and
  `site_tagline` are one home; the fifteen `legal_*` settings
  (`legal_business`, `legal_address`, `legal_email`, `legal_phone`,
  `legal_country`, VAT, company number, ...) are another, written from the
  Legal pages screen. `legal_business` and `site_title` are the same fact
  stored twice. The wizard must write into what exists rather than open a
  third home -- and consolidating the two may be the honest first step,
  since "single source of truth" is not true today.
- **`_apply_pack_identity()` is a heuristic that the wizard can retire.**
  It gives the site the template's name, guarded by "only if the current
  name is still somebody else's demo" -- a set of "", "My Site", "Your
  Business Name" and every builtin's own `business_name`. That guard is a
  good guess in the absence of an answer. Once the wizard has recorded
  that the owner stated their identity, there is an actual answer, and the
  path should simply not fire. Keep the heuristic for sites that never ran
  the wizard.
- **A small live bug in the same function.** The guard tests the TITLE,
  but the write covers title AND tagline. So an owner who typed a tagline
  while the title was still "My Site" loses the tagline the next time a
  template is activated. Each field should be judged on itself.

**The saved template takes the site's name.** That answers what was open:
the name the owner gives IS the name of the template saved at the end.
`save_current_site_as_package()` already auto-names a save
"<active template> - <timestamp>" when handed no name -- that stays the
fallback for the snapshot-before-a-destructive-step case, not for this
one. A second run producing a template whose name already exists is
already a solved problem: the import conflict rules (overwrite / keep both,
which renames with a +1 / cancel) apply unchanged.

**Should the details be baked into the template?** Partly. The proposal is
that the saved template carries the owner's details, so activating it
applies them. It is right for one case and dangerous in another, and the
two are separable.

Where it is right: **your own template as a restore point, and moving
hosts.** Export here, import there, and the site comes back whole rather
than nameless.

Where it is not: **a template is a shareable artifact.** `export_package_zip()`
is an always-available action on any library entry. Bake the identity in
and exporting your site hands whoever receives the zip your business name,
postal address, phone, email, VAT number and company number. Today that
cannot happen -- only the hand-authored builtins carry `business_name`/
`tagline`/`footer_blurb`/`footer_contact`, and those are invented names
for invented bakeries. `save_current_site_as_package()` captures no
identity at all. Adding it without a second thought turns every shared
template into a disclosure.

**Never the connections or the keys; content and the site name are fine.**
That is the line, and the manifest side already holds it by construction:
the only setting `_build_package_dir()` reads is `nav_layout`. No API
keys, no SMTP, no Stripe or Cal.com settings, and commerce is not captured
at all -- the word "stripe" does not appear in `packages.py`. Keys live
encrypted in settings via `crypto.py` and never go near a package. Nothing
to fix there; it is worth writing down so nobody helpfully adds it.

A connection can still travel as content -- the Embed tool exists to hold
third-party markup, so a captured page can carry a Cal.com address or a
Stripe button, and pages ARE captured. **But calling that a leak was
wrong.** That markup is served to every visitor of the site it came from.
A copy reveals nothing, and it is of no use to anybody unless they
actually want to book or buy -- from the original owner.

The real failure runs the other way, and lands on whoever INSTALLED the
package: their site now carries a Pay Now button wired to somebody else's
Stripe account, or a booking that drops into somebody else's calendar,
looking for all the world like part of the template. Money and
appointments go to the wrong party, quietly, and the importer has no way
to tell by looking.

The same correction applies to the business details. An Impressum is
public by law -- the address did not escape. The problem is that the
importer's terms page would name the wrong legal entity and the wrong VAT
number.

So the concern is misattribution, not disclosure, and the rule is about
pointing rather than hiding: content naming a specific real-world party --
a payment account, a calendar, a legal entity -- must not silently keep
pointing at that party on somebody else's site. **That makes it an
install-time concern only**, which is simpler than what was written here
first: nothing needs stripping on the way out. The precedent is already in
the codebase -- a package ships its Blog tool with `data-blog-id=""` and
the installer fills it in, because a package cannot know what id a blog
will get elsewhere (`routes/admin/__init__.py`). A third-party reference
wants the same treatment on the way in: filled from the receiving site's
own integration, or left visibly unconfigured.

None of the sixteen builtins carries one today, so none of this has bitten
yet.

The shape that gives both:

- **A package may carry an identity, and on apply it is only ever a
  fallback.** Used when the site has none of its own; never an overwrite.
  That is already precisely what `_apply_pack_identity()` does, which is
  why the builtins work: a fresh install gets "Flour & Salt", an owner who
  has said who they are keeps their own name. So an imported package,
  however it was authored, cannot take over an identity somebody stated.
  The invariant holds and the feature still works.
- **The choice belongs at export, not at save** -- but for a plainer
  reason than secrecy. "I am moving this site" carries the details; "I am
  sharing this look" does not, and that is the default. Not because a
  business address is confidential (it is on the site's own legal page)
  but because a shared template that arrives already claiming somebody
  else's company is wrong on the receiving site, and wrong in a way its
  new owner will not notice until it matters.
- **And mostly the question does not arise**, because the details never
  left. Identity is site data; loading a template does not touch it. There
  is nothing to restore unless the whole install is gone -- which is the
  moving-hosts case above, and is also what `services/backup.py` is for.

So: bake it in, as a fallback that cannot overwrite, and make including it
in an export a deliberate answer to a question rather than the default.

**Decided.**

- **It offers itself once.** The prompt on first edit fires one time,
  ever. After that the wizard exists only behind its button under
  Templates, retriggered deliberately. So there is no "do not ask again"
  to build -- declining IS not asking again -- but there does have to be a
  way back in that an owner can find, which is what the button is for.
- **It remembers.** Both what was chosen and where it stopped, so leaving
  halfway and coming back continues rather than restarts, and a retrigger
  a year later opens with last time's answers as the defaults rather than
  with blanks. That makes the stored state a real record of the site's
  setup, not a scratch value to be cleared on completion.
- **The name is asked first**, and skipped if the owner has already given
  one. "Already given" is the catch: a fresh install is called "My Site",
  and the moment a template is activated it is called "Flour & Salt" --
  the template's name, not the owner's. Neither counts. The test for this
  already exists and should be reused rather than rewritten:
  `_apply_pack_identity()` in `routes/admin/__init__.py` builds the set of
  names that are not anybody's -- "", "My Site", "Your Business Name", and
  every builtin manifest's own `business_name` -- precisely so activating
  a theme cannot overwrite a name a person typed.

**Still to decide.** Whether finishing renames the saved template to the
name the owner gave, or whether that is a separate question at the end.
Whether the AI steps get the `cmsElapsedTimer` counter -- they will be
slow enough that they should.

## 2026-08-25 - One corner scale, and two scripts hiding in a title

The backlog said "two corner conventions, 6px and 4px". Counting them
found seven — 4, 5, 6, 8, 10, 12 and a pill — across 122 declarations in
four stylesheets, and the real problem was not the count. **The same ROLE
differed by file**: a button was 4px in the editor's toolbar and 8px on
the admin screens. Nothing looked wrong; the next control simply had
nothing to follow.

Owner's choice of the two candidates: the editor's values win, since that
is where most of the app's controls live.

    --cms-ui-radius-control  4px   button, select, input, textarea, chip,
                                   swatch, colour well, badge that size
    --cms-ui-radius-surface  8px   panel, toolbar, menu, dropdown, dialog,
                                   card, log, preview, thumbnail
    999px                          a pill is its own shape and stays

Every one of the 122 was classified by hand and named in the mapping,
rather than matched by pattern — because a pattern got it wrong on the
first attempt in the direction that matters: `.cms-menu-newpage-title` and
`.cms-menu-custom-url` are text inputs whose names say neither, and would
have been rounded as surfaces. Result: 4 pills untouched, 1 scrollbar
thumb skipped, 117 tokenised, 76 actually moving a pixel. Measured after,
in the browser: the chrome uses 4px, 8px and 999px and nothing else. The
other radii on the page are the SITE's — `--site-radius` at 22px on
sections and banners, and the Corners picker's own swatches, which vary
because they are previews of that setting.

**Then the admin dashboard's browser tab read:**

    Dashboard — My Site Admin<script src=/static/js/admin/backups.js></script>

A `<script>` had been appended inside `{% block title %}`, so a browser
parsed it as the title's text and never ran it. That script is what puts
the confirm dialog on this page's `[data-confirm]` button — so **"Remove
pages left behind by other templates" deleted them on the first click,
with nothing asked.** Exactly the failure the × on a section nearly
shipped once.

Scanning for the pattern found a second: `commerce_bookings.html` hid
`bookings.js` the same way, and there it is worse — that script IS the
Cancel button's click handler, so the button did nothing at all when
pressed. Both moved to the end of their content block. A sweep of all 22
admin GET pages: no markup inside any `<title>`, nothing failing.

Worth keeping: the bug was invisible in the app and plainly legible in the
browser's tab caption. It surfaced while screenshotting something else.

## 2026-08-25 - A dead strip down one side, and three buttons in a squeeze

Both reported from a phone, with a line drawn down the wasted space.

**The Tools chips.** The grid is `repeat(auto-fill, 84px)` — a fixed
column width, so it works out how many columns fit and then abandons
whatever is left over. In a 220px panel that is two columns and ~56px
stacked against the right-hand edge, with ~10px on the left. The panel did
not look padded, it looked mis-hung. It is `minmax(84px, 1fr)` now: same
column count (a column is still at least a chip wide, which is what
decides the count), remainder shared between the columns. And the chip
itself was pinned to 84px inside its own track, which merely moved the
waste from the end of the row into every gap — it fills its track now.
Measured after: chips 95px, identical, zero gap at both edges.

auto-fill and not auto-fit, deliberately: auto-fit collapses empty tracks,
so a group holding one tool would stretch that chip across the whole panel
while its neighbours stayed chip-sized.

The other side-dock galleries — colours, fonts, templates — were already
`repeat(2, 1fr)`. The Tools grid was the only one measuring its columns
instead of dividing them.

**The confirm dialog's buttons.** Three of them is the normal case here,
not the exception: every template confirm offers Cancel / Just the look /
Take everything. The row could not wrap and the buttons could shrink, so
on a phone they squeezed instead of moving — "Just the look" broke across
three lines and the three came out different heights and ragged. The row
wraps now and the buttons do not shrink: each keeps its label on one line
at its natural width, and whichever does not fit drops to the next line,
still right-aligned. What a button says decides its width; the dialog is
what gives. At 375px: all three 35px tall, one line each, two rows.

## 2026-08-25 - Three backreferences that were never backreferences

Chasing why the render check moved after a CSS-only change turned up two
things, and the second was the real one.

**The cache-buster.** Stylesheets are linked as `?v=<mtime>`, so editing
any CSS file changes the page — by a ten-digit number, which means even
the byte count stays identical. It reads exactly like the renderer moving
while nothing rendered differently at all, and it cost a full
investigation before that was clear. Normalised now, alongside the row
ids and the captcha: this check is about markup, and a cache-buster is
not markup.

**Three control bytes in the normaliser.** Reading those lines closely,
each carried a literal 0x01 where a `\1` backreference was meant. Same
cause as the NUL in the entry above, one layer earlier: an escape written
through a shell heredoc arriving as the byte it names. They have been in
the file since the check was written.

The captcha one was harmless — a constant replacement normalises fine.
The other two were not:

    data-section-id="12"  ->  chr(1) + '="N"'
    data-tool-id="12"     ->  chr(1) + '="N"'
    data-blog-id="12"     ->  chr(1) + '="N"'

Three different attributes normalised to one identical string, and
`id="section-5"` to the same thing as `id="tool-panel-5"`. **A tool could
have swapped a section id for a blog id and this check would have called
it unchanged.** They are lambdas now, with nothing left to escape.

Both hazards are the same shape as the NUL: something written *about* the
code, through a layer that eats backslashes, landing as a byte instead of
as text. Worth remembering that the file tools do not have this problem
and a heredoc does.

Baseline re-recorded, and a `touch` on a stylesheet now leaves it
untouched.

## 2026-08-25 - Six chrome surfaces stop borrowing the site's colour

Measured rather than trusted, because the count in the backlog had no
method recorded with it. Signed into a throwaway host in a real browser
and asked, of every element carrying a `cms-` class: does it paint a
background of its own, and is its computed colour the same as the body's
purely by inheritance?

Ten came back, and the classification was the point:

- **Six were chrome** and are now fixed: `.cms-menu-pages-dropdown`,
  `.cms-icon-grid-view`, `.cms-banner-text-config-grid`,
  `.cms-wysiwyg-toolbar`, `.cms-modal-backdrop`, `.cms-modal`. They take
  `--cms-ui-text: #111827` — not a new value, but the one this app's
  inputs, selects and panel text already use, so nothing on screen moves
  and the inheritance path closes. Declared in `cms-modal.css` as well as
  `inline-editor.css`, the way `--cms-ui-accent` already is in two files,
  because the dialog is used on admin screens where the editor's
  stylesheet is not loaded.
- **`.cms-newsletter` is site content** on a site background. It is
  supposed to take the site's colour. Left alone.
- **`.cms-lightbox` was the real find.** It is site-facing, so it looked
  like the newsletter — but it is a fixed 85%-black overlay, and it was
  taking the bakery's dark brown for its text. Nothing showed it, because
  the only text in there is a close button that pins white. The case that
  would have shown it: an image that fails to load, whose alt text the
  browser then draws in the inherited colour, on black. It pins white now,
  which is what its own close button already said.

Verified after: one element still inherits, `.cms-newsletter`, correctly.
Every text-bearing descendant inside the six now resolves through a chrome
ancestor (#111827, #374151 or black) and none through the site — and none
of them changed value, which is the evidence that nothing moved visually.

The rule is in CLAUDE.md now rather than only in a count: a surface that
paints a background states what colour text on it is.

## 2026-08-25 — Two hosts, the same page, down to the byte

The last random token in a rendered page is gone. An accordion FAQ named
its `<details>` group `cms-faq-` + `uuid4().hex[:8]`, so the same template
installed on two machines produced pages differing by those eight
characters — invisible, harmless, and the one thing standing between this
project and "the same template is the same site anywhere".

It is derived now, from the set's own name and its questions. Not a new
convention: this file already derives a question's id from the slug of its
own words, and the group name had simply never been held to it. The name
is in the seed because `data-faq-name` exists precisely to tell two sets
on one page apart; two blocks matching on both the name and every question
are the same set shown twice, and the app has nothing else to tell them
apart by either.

Two more random tokens turned up next to it, and they mattered more.
`build_faq` fell back to `uuid4()` for a question with no stored id — and
`BLOCK_LIBRARY["faq"]`, the starter block every FAQ tool begins as, is
built at **import** time. Every container therefore had its own starter
markup. It uses `faq_slug()` now, so the starter reads
`data-faq-id="how-long-does-it-take"` and is identical everywhere.

Verified by building two fresh hosts from nothing and hashing every page
of all 16 templates in the visitor view: **79 pages, 44 accordion groups,
identical** — with one deliberate exception. Every `contact` page differs,
and must: it carries the spam question ("What is eight plus four?") and
its signed token, which are a security control and are supposed to be
different every time. That is the whole remaining difference between two
installs of this app.

Two process notes, both bought the hard way. The comparison first reported
"byte-identical" across 16 pages with 0 accordion groups — it had compared
two untouched sites, because a fresh install redirects every admin POST to
`/admin/account` until the generated password is changed, so nothing was
ever activated. **A comparison that passes without exercising the thing it
compares is worse than a failing one.** And the `NUL` separator in the
first version of the derivation was written into the source as real NUL
bytes, which took the container down on boot; it is `chr(31)` now, the
same reason this file writes `chr(10)` instead of an escape.

## 2026-08-25 — One Image tool, and a net with a hole in it

Second tool through the unification, and it closed a backlog item of its
own: "column-cell images have no Caption or Width".

The gap, measured before touching anything. A picture in a section
offered a link, an animation, a **width**, **five** cut-out shapes, a
**caption**, and upload/generate/library. The same picture in a column
offered a link, an animation, **two** cut-out shapes, and
upload/generate/library. No width, no caption, three shapes missing —
again, differences nobody chose.

Both now call `image_controls()` and `image_tool()`. Verified where it
counts, in a column cell on a running site: link, animation, width,
cut-out, caption, upload, generate, library all present, six shape
options, the shared `block block-image` markup, and a caption that
saves (`caption` added to the column-cell update route) and renders —
as a real `<figure>`/`<figcaption>`, so a screen reader reads the words
as part of the picture rather than as a stray paragraph under it. No
caption, no wrapper, so existing markup does not shift.

**Then the safety net failed, which is the more useful half of this.**
`tools/render_check.py` exists precisely because "the Image tool grew a
Caption and a Width select as a section and neither as a cell" — its own
docstring says so. Running it, `block-text` had vanished and every hash
had moved. Neither was a regression:

- Its block regex was `<section class="block block-([a-z]+)"`, anchored
  at the closing quote. That matches a block whose class is *exactly*
  `block block-x` and nothing else. An Image carries its width, cut-out
  and animation as classes; anything in a column carries
  `cms-column-body`. **So the check never hashed a single Image, or a
  single tool in a cell — the two things it was built to watch.** It
  hashed the whole page, which moved when anything moved, and named
  `block-html` twenty-three times.
- `block-text` disappearing was my own doing: `class="block block-text
  {{ extra_class }}"` leaves a trailing space when there is no extra
  class, and the anchored regex stopped matching. Both macros now build
  the class list and `join(' ')` it, so the attribute is one tidy string
  — the Image one had been spread across three lines of Jinja, carrying
  newlines and indentation into the markup.

The baseline was also five commits stale — recorded 2026-08-24, never
refreshed through Contacts, the Text unification or the background
picker. A net nobody re-pegs is a net on the floor. It is re-recorded
now (30 tools, Image and Text among them at last) and stable across two
runs.

Regression: all 17 templates, every page, both views — 0 problems, no
editor markup in a visitor page.

## 2026-08-25 — One Text tool, and the wrong direction first

Reported as "there are still 2 different text type tools, one in the
footer and one in the body". Both were Text; the footer's was a Columns
*cell* and the body's was a *section*, so they came out of the two
different renderers — the concrete face of "one renderer per tool".

Measured rather than guessed: a cell's Text had no Corners or Depth
control while every other cell tool did, and it carried none of the
tool-level attributes those controls write.

The first fix was the wrong way round. Adding Corners and Depth to the
cell made them match — and then the body's Text was the odd one out,
because the section chain withholds them on purpose:
`tool_can_be_shaped = s.type != 'text' and not s.is_divider`, with a
comment already explaining that Text paints no box, so the control would
do nothing and read as a bug. **The rule existed; only one of the two
renderers knew about it.** That is the whole argument for one renderer,
in one line.

Text is now a single `text_tool()` macro called from the section chain
and from `render_cell`. Both places: 15 formatting buttons, identical
markup (`<section class="block block-text">`, plus `cms-column-body` in a
column for its own layout), same decision about Corners. The one
remaining difference belongs to the container rather than the tool — a
cell's Text can be cleared out of its cell, a section is deleted as a
section — and both are reachable either way.

**And the fix was still not done, because the check was wrong.** The
toolbar was counted in the DOM rather than on screen, so both places
reported 15 formatting buttons while the footer's ribbon was
`display: none`. What a screenshot showed and the count did not: a Text
tool in a footer column opened to its name and a remove button, with no
formatting at all. The ribbon is hidden by default and was revealed in
exactly two places — a plain Text section on focus, or a header already
moved into the shared slot at the top of a Columns section — and a cell's
own panel is neither. One rule now reveals it in any open tool panel,
wherever that panel stands, and all four Text tools on the page show 16
clickable controls.

**Measure what a person can see.** Counting nodes in the markup answers a
different question from the one being asked, and it answered it
confidently twice.

Open question left with the owner: Text has no Corners/Depth *anywhere*
now, which is the pre-existing documented decision. If the intent is that
every tool's toolbar carries every control regardless, that is one line
in `tool_can_be_shaped` — but it would mean shipping a control that
demonstrably changes nothing on a block with no box.

## 2026-08-25 — A rule written into the middle of a selector list

The template tiles down the side were different heights and every one of
them wore an accent ring. Both from one edit of mine, earlier the same
day: the "which preset is current" rule was written INTO an existing
comma list rather than after it, splitting the list in two. What had been

    .cms-tpl-choice,
    .cms-color-preset-swatch,
    .cms-font-preset-btn { height: 58px; justify-content: center; }

became `.cms-tpl-choice, .cms-color-preset-swatch.is-current { outline… }`
plus a height rule for the two selectors left behind. So the template
tiles took the ring meant for a current preset and lost the height that
made them a set — the names that wrap to two lines, "Garage / Mechanic"
and "Self-Help & Wellness", grew and the grid stepped up and down.

Measured after: 16 tiles, one distinct height (58px), 0 stray rings, and
the active template still marked by its own darker border and tint.

**A rule inserted into a comma list changes what the list means.** It
reads as an addition and it is a subtraction. The same shape as the
specificity collision earlier today: both times the CSS I had written an
hour before was the thing fighting me.

## 2026-08-25 — A dialog taller than the phone

"It pops up with images but position is fixed, top and bottom cut off."
Exactly right, and the cause is a familiar one: the backdrop centres its
child with flexbox, and **a flex-centred child that outgrows its
container is clipped at both ends with nothing to scroll to**. The
overflow goes above the top of the scrollable area as well as below the
bottom, so neither end can be reached.

Three things together, none of which works alone: padding on the backdrop
so the dialog never touches the edges, a max-height on the dialog in dvh
(so a phone's address bar sliding away does not leave it overhanging),
and the grid itself scrolling rather than the dialog — which keeps Cancel
where it was put instead of somewhere below the fold. Tiles also drop
from 140px to 96px under 560px wide, since four across at 140 is wider
than the screen and made the grid feel stuck as well as cut off.

Measured with 105 pictures:

    375x812   modal 67-745 of 812, grid scrolls 6625px, last tile
              reachable, Cancel visible, tiles 126px
    1280x800  modal 62-723 of 800, grid scrolls, Cancel visible,
              tiles 153px

The max-height is on `.cms-modal`, so every dialog in the app inherits
the fix — the confirm prompts and the icon grid included.

## 2026-08-25 — The first edit makes the site yours

Two things, both from "I only see 3 images" and the reasoning that
followed it.

**The picker offered the wrong half of what exists.** It listed the
owner's uploads and the ACTIVE template's pictures — so a site that had
been through three templates could not choose the picture already sitting
on one of its own sections, because that picture came from a template it
had since left. Every installed template's pictures are offered now, the
active one's first, and the Library button behind Image, Banner and Card
was given the same set: 144 on this install, against 53. Two pickers
offering different halves of what exists is worse than either.

**And a built-in can never hold somebody's work**, because it is
reinstalled from the image on every boot. So the first content change now
forks: the site gets a copy of the template it was using, activated in
its place, carrying the admin's colour/font/shape overrides and the
header and footer sections with it. From then on they are editing their
own site.

    activate bakery      -> Bakery, builtin, 16 templates
    first edit           -> "Bakery (your copy)", 17 templates, edit landed,
                            bakery itself untouched
    second edit          -> still 17 — it forks once, not per keystroke

A copy of the PACKAGE, not a fresh capture of the site: capturing would
rescan and re-copy every picture on the first keystroke, and what is
useful to own at that moment is the template they started from.

Saving then means what it says: **Update "<name>"** rewrites that
template's package from the site as it is now, or **Save as New Template**
collects another copy. Overwrite is refused for a built-in, since it
would last until the next restart.

## 2026-08-25 — A picture you choose becomes yours

The defect: a page pointing into a template's own folder 404s the moment
that template is deleted. Proven earlier — an owner's page, a template's
picture, delete the template, broken image. Permanent for an imported or
saved template; for a builtin it heals at the next boot, which only makes
it intermittent.

Fixed by copy-on-use rather than by moving everybody's pictures into one
pool. When somebody CHOOSES a template's picture for their own content —
a section background, a page background, or the Library button on an
Image, Banner or Card — it is copied into the library and the copy is
what gets stored. One file per choice.

    chose  /static/themes/bakery/media/bakery-shop.png
    stored /static/uploads/23afb8c4….png        (1 file copied)
    delete the bakery template
    the owner's picture still loads: True
    the template's original is gone: True

**The distinction that makes it cheap**: a template applying its OWN
content is not a choice, so it does not adopt. Verified by activating all
sixteen templates in a row — 0 files copied, and the 3 sections that came
from a template still point at that template's copy. Unpacking every
template's media into one library at install would have moved 86MB and
made every template's pictures editable by anyone; this moves one file
when somebody actually reaches for one.

The rule: **the app's own assets stay the app's; the moment a person
picks one, it becomes theirs.** Same reasoning as the tools' controls
being the app's and the content being the site's — ownership decides
lifetime.

## 2026-08-25 — "Change the template, keep my content"

Asked as a design question and it turned out to be a missing button. The
server has always supported it: activating a template without `force`
applies the theme, palette and fonts and SKIPS the content, because
replacing something is what needs confirming. Nothing in the interface
ever asked for that — the dialog offered "Activate" or Cancel, and Cancel
meant do nothing at all. So the most common want of all, a new look on
the writing you already have, was reachable only by posting the form
yourself.

Three answers now: **Take everything**, **Just the look**, Cancel.
Verified both:

    start            template=bakery  clinicCss=False  ourWords=True
    Just the look    template=clinic  clinicCss=True   ourWords=True
    Take everything  template=clinic  clinicCss=True   ourWords=False

**A capability with no way to ask for it is not a feature.** This one had
a route, a conflict check and a comment explaining the reasoning, and no
button.

Worth recording alongside it, from the same conversation — what the two
export paths actually do, since the names suggest otherwise:

- **Export** hands over THE TEMPLATE: the pages and pictures it shipped
  with. Not your edits, not your uploads. Verified: an uploaded picture
  used on a page was absent from the zip.
- **Save current site as a new template** hands over YOUR SITE: it scans
  the live content and packs every picture it references, uploads and
  template media alike. Verified: the saved package contained both.

And the flaw the same test found: a picture referenced from a template's
own folder 404s if that template is deleted. For a builtin it heals at
the next restart, because the seed reinstalls it; for an imported or
saved template it is gone. The fix is copy-on-use — when somebody picks a
TEMPLATE's picture for their OWN content, copy it to the library and
point at the copy — so user content never depends on a template's
lifetime. Not built yet.

## 2026-08-25 — Pictures chosen by sight, and a circle that was an egg

The background control shipped as a list of filenames.
"bakery-band-2.png" tells nobody what is in it, so it is a thumbnail grid
now — the same `cmsImagePicker` the editor already had for choosing
between freshly generated images, given the library as a JSON data block
rather than script built per template.

Which immediately showed something worse: **the picker was empty on a
fresh site.** The library lists UPLOAD_FOLDER only, and a template's own
pictures live in its package under static/themes/<slug>/media/ — so a
bakery whose footer is full of photographs offered nothing to put behind
a section. The picker now offers the owner's uploads first and the active
template's pictures after them. 10 to choose from on a fresh install
instead of none.

And the remove × was an egg on 8 of 11 panels: 20 wide, 28 tall. The
panel sizes its controls to a common 28px row, which is right for a
select and wrong for a circle, and it beat the button's own size because
it was the more specific selector. Only the buttons that happened to sit
outside a panel — in a Columns cell — looked right, which is why it read
as "some toolbars".

**A shape is a property of the thing, not of the row it stands in.** The
row was right to size its selects; it was wrong to size everything.

## 2026-08-25 — Where the background lives, and a bar that never said its colour

"How does the Call to Action tool have its background image assigned? I
don't see a way to do it from the tool or the section toolbar." It was
there, in one place only: select the section, open the Colours panel,
find Selection. Exactly the three-steps-away problem Corners had before
it moved onto the section's own bar — and a background is the FIRST thing
somebody looks for when a band of the page is a photograph.

The picture, its dim and its position are on the section bar now, same
field as the panel's copy so the two are one setting shown twice. Dim and
position only appear once there is a picture for them to act on, so the
bar does not carry three controls for a section that has none.

Then the bar's own text: "Divide" was unreadable, at **1.51:1**. The
toolbar paints itself dark and never said what colour its writing was, so
its labels inherited the SITE's text colour — near black on dark navy for
any template with dark body text.

**And the first fix did not work**, which is the part worth keeping: a
rule I had added earlier for chrome (`.cms-inline-form label { color:
#374151 }`) had the same specificity and came later in the file, so it
won. Two of my own rules, disagreeing, and the loser was the one written
for this exact bar. Measured after: 54 pieces of text on the section
bars, worst 12.53:1, all above 4.5.

**When a fix does not take, check what else you wrote.** The instinct is
to look for a stray theme rule; twice today it was a rule of mine from an
hour earlier.

## 2026-08-25 — Three kinds of mark, one size

"The copyright icon appears to be a different start size to the other
icons." It was, and so was everything else — measured at one font-size of
24px, an emoji drew 33px, a brand SVG 24px and © 17px. Three different
answers to "the same size", because they are three different kinds of
thing: an emoji is a picture drawn to fill its line, an SVG is exactly
the size it is told, and © is ordinary typography.

`render_icon` now says which kind a mark is, and the CSS draws each at
the size it needs to LOOK like the size that was asked for, then gives it
a box that undoes the adjustment:

    emoji  0.74 × size, box 1.35em  ->  1.00 × size
    text   1.38 × size, box 0.72em  ->  0.99 × size
    drawn  1.00 × size, box 1.00em  ->  1.00 × size

Measured after, at 24px: drawn widths 24.4 / 24.0 / 23.4 / 24.4, boxes
all 24, one shared line height. With the switch off and the size
inherited: 17.8 / 17.5 / 17.1 / 17.8, boxes all 17.5.

**The trap in the middle**, and the reason the first attempt only half
worked: a custom property carrying `1.25em` is substituted where it is
USED, not where it is declared. A box written as
`var(--cms-contact-icon, 1.25em)` therefore resolved against whatever
font-size each kind had just been given — so the © sat in a 30px box and
an emoji in a 16px one while both marks drew at 17px. Each box has to be
expressed in the icon's OWN em for the maths to close.

## 2026-08-25 — A slider for the marks, and remove in every corner

The size control became a switch and a slider, and it sizes the **icon**
only. Off — the default — the block says nothing about size and the marks
follow their own line, which is right nearly everywhere. On, the number
is the owner's, 12 to 48, clamped at both ends. Measured: at 48 the mark
is 48px while its words stay at the 14px the zone gives them; switched
off it returns to 17.5px, inherited.

The value rides as a custom property rather than a class, because it is a
number somebody dragged to rather than one of three names. Off writes
nothing at all, so the block goes back to inheriting rather than to some
remembered default — the difference between "no opinion" and "medium".

And remove now sits in the corner of every tool's panel, not only those
in a Columns cell. A tool that was its own section had its × on the bar
above instead, so the same control lived in two places depending on where
the tool happened to be standing. For a section, removing the tool IS
deleting the section, so it asks first — 8 of the 11 panels on the test
page ask, the 3 in cells just clear the cell.

**Nearly shipped a × that deleted a section without asking.** The
confirmation is bound to `.cms-delete-form`, and the new form carried
`data-confirm` alone — which does nothing on its own. The attribute
looked like the mechanism; the class is the mechanism.

## 2026-08-25 — Contacts: closer, and a size to choose

The mark and its words are one thing, so they now sit like one thing —
4px apart rather than 7, which had them reading as an icon and a separate
label beside it.

And a size: small, medium, large, chosen in the tool and stored on the
wrapper. The words and the mark scale together, and the brand SVGs come
along because they are sized in em rather than in the 16px their own
attributes ask for — a detail worth remembering, since an SVG with width
and height attributes ignores font-size unless the CSS says otherwise.

    Small   text 12px · icon 13.8px · svg 14px
    Medium  text 14px · icon 17.5px · svg 18px
    Large   text 17px · icon 22.9px · svg 23px

Medium is what a block written before the choice existed does, so nothing
on an existing site moves.

## 2026-08-25 — Saved, but not shown; and a choice of arrangement

The save landed and the page did not move until it was reloaded. The
editor swaps a rebuilt tool into `.cms-block-host` after a save, and the
Contacts output had no such host — neither the cell's `.cms-column-body`
nor the generic html preview carried it, because only the eight declared
blocks ever had. Both are hosts now, which is the same fix for every tool
rendered through those two places.

Three failures in a row on this tool, each one a different link in the
same chain: the route did not answer in JSON, then the answer had nowhere
to go. Worth naming: **"it saved" is three things — the write, the reply,
and the redraw — and only the first is visible from the database.**

Also added, because a footer strip and a sidebar want opposite things: a
Contacts block sits its lines side by side or one per line, chosen in the
tool and stored on the wrapper like everything else it remembers. Side by
side is the default, so nothing on an existing site moves.

## 2026-08-25 — Saved fine, said it failed; and controls that do nothing

"Auto save fails", with the entries appearing on the page underneath the
box that had just said it could not save them. Both halves were true: the
save worked, and the report was honest about what IT saw. The editor's
apply-on-change posts and reads the answer as JSON — every other tool
hands back `{ok, html}` so the block can be swapped in place — and these
two routes returned a redirect. `res.json()` threw, and the catch says
"check your connection".

Worth keeping as a shape: **a save that works and reports failure is
worse than either.** It teaches the owner to distrust the thing that is
actually fine, and there is no way to tell from the message which half
went wrong.

The other half of the same screenshot: Corners and Depth were being
offered on a tool that paints no box. `.cms-contact-tool` and
`.cms-contact-detail` set no background, border or shadow — the only
radius rules with "contact" in them belong to the Contact FORM's status
messages — so both controls were inert. Withheld by the same rule Text
and Divider already use. Checked the other way too: Numbers, Call to
action and Email sign-up still offer them, because those do paint
something.

**Before offering a control, check it changes something.** The test is
not "does this tool have a box in principle" but "does anything in this
tool's own CSS read the value".

## 2026-08-25 — Remove goes in the corner, on every tool

Three from one screenshot.

The icon button was printing `brand:x` as words. The server rendered the
mark correctly; the JS that runs when you PICK one wrote the key instead —
`textContent = key` where the grid button beside it already held the drawn
mark. Copying its contents is the fix, and it is why a network now shows
as its logo rather than as its name.

There was no © in the picker. The tool had carried its own short icon list
before, and dropping that for the app's full set lost the one character a
footer actually needs. © ® ™ are in Symbols now, where somebody would
look.

And **remove belongs in the top right corner of the panel, on every
tool.** It was the last item in a wrapping row, so where it landed
depended on how many controls the tool had and how wide its column was:
top right on a Divider, bottom left under two selects on Contacts. A
control that deletes the thing you are looking at has to be in the same
place every time. Measured after: 3 of 3 open panels put it 3px down and
5px in, whatever the tool.

The general shape, again: **a control's position should be a decision,
not a consequence of how much else is in the box.** Same as the tool
name, which moved to its own line for exactly this reason earlier today.

## 2026-08-25 — No kind: the value already says what it is

The dropdown had to go. A line reading "Phone" beside a WhatsApp link is
a question the app should not be asking, and the answer was already in
the box: four rules in order — starts with http or /, an address; an @
with no slash, an email; starts + or a digit and reads as a number, a
phone; a dot or a slash, an address; anything else is words, and words
are not a link. A line is now an icon and a value, nothing else.

Which put the whole weight on the icon, so the brand marks moved into the
icon set where they belong. `render_icon` draws a `brand:` key from a
path and everything else as the character itself, so the picker offers
512 icons including the seven networks — a footer's Instagram is the
Instagram mark, not an approximation, because no emoji means Instagram
and a row of near-misses reads as a mistake.

Nothing loses its marks: `LEGACY_KIND_ICONS` maps the kinds two earlier
shapes of this tool stored onto the icons they implied, and one loop in
`read_contact_tool` reads all three shapes — the fixed-field one, the
kind one, and this. A template's `footer_contact` maps the same way, so
what sixteen templates ship still opens with its own icons.

**And the same mistake, a third and fourth time.** Replacing a range of
lines between two anchors took `MEDIA_TYPES`, the divider and breadcrumb
tables, `_classify_layout_chunk` and five other functions with it, twice,
and the app would not boot. The rule that finally worked: restore the
file, apply each change as an exact-string replacement with its own
assertion, and diff the set of top-level names before and after —
"names lost besides the intended: none" is a check, "it parses" is not.

## 2026-08-25 — The Contacts row, as it should have been

Six corrections after using it, each one worth keeping as a rule.

- **A row is a row.** Kind, icon, value, tick box, + and − on one line.
  It had been a stack of labelled fields, which is a form; this is a
  list, and a list of five contacts should read as five lines.
- **Label by tooltip, not by text.** "Line 3", "Icon", "Print" is three
  words of furniture per contact and nothing a person needs twice.
- **The + belongs at the end of the row it acts on.** A stepper at the
  top can only add at the bottom, which is the wrong end when the line
  you are looking at is in the middle. `add_2` puts a line under the
  third, `del_2` takes that one away.
- **An icon is chosen by looking at it.** The picker shows the app's
  whole set — 505 icons, the same grid the Menu tool and the WYSIWYG use
  — and the button shows the chosen glyph and nothing else. A dropdown
  reading "🔗 Link" was a list of names with pictures attached.
- **The type is read from what was typed, not from the dropdown.** Four
  rules in order: starts with http or /, it is an address; an @ with no
  slash, an email; starts + or a digit and reads as a number, a phone;
  contains a dot or a slash, an address. Anything else is words, and
  words are not a link — which is what lets a copyright line and a
  street address sit in the same list. The dropdown is left to choose the
  icon.
- **It has to save as you type.** Adding a row and filling it in did
  nothing, because this form alone had been left off the
  apply-on-change class the other tool panels use — my own doing, from
  worrying that a submit mid-typing would be worse than a submit that
  never came.

One thing that needed real thought: a line with nothing in it must not be
published — a visitor should not get an empty link — but where it was has
to survive, or pressing + on the first line puts the new one at the
bottom. The wrapper carries `data-blanks` and the reader puts the gaps
back, so the page stays clean and the form stays faithful.

Verified: + on line 1 inserts in the middle, − removes the line it sits
on, an unticked line renders as its icon alone with the value on hover,
and 79 pages across 16 templates render in both views with no failures.

## 2026-08-25 — Contacts as rows: a kind, a value, and a + for more

The fixed-field version built earlier the same day was the wrong shape.
Asked for instead: a line is a **kind** and a **value** — pick Instagram
from a dropdown, type the handle — with a + for another line, defaults or
a custom kind with an icon of the owner's choosing, and the tool works
out whether what was typed is an email, a web address or a phone number
so the link is right. It can carry a copyright line too, which is what
lets it replace a template's free-text footer.

Thirteen kinds (phone, email, website, address, seven networks,
copyright, "Something else"), each bringing its own icon and its own idea
of a link. `contact_link()` is the guess a person makes looking at the
value: an @ with no slashes is an email, digits and punctuation are a
phone number, anything else is a web address with `https://` added when
it was left off. Verified across all five shapes, including a custom row
pointing at wa.me with a chosen icon.

The `+` is a submit, exactly like the Accordion's panel stepper, so it
works without JavaScript and a value typed in the same submit still
lands. An empty row cannot live in the markup — the markup IS the storage
— so the wrapper carries `data-rows` and the form pads back to it: a line
being filled in survives the round trip without being published.

**A phone number is written, not stored.** The reader first took the
value from the href, which meant "01233 555 019" came back as
"01233555019" — the app quietly reformatting somebody's number the first
time they opened the form. The text is the owner's copy; the href is the
dialling copy.

**Template footers build through the same function now.** A manifest's
`footer_contact` is already `{kind: value}`, which is exactly a list of
rows, so what a template ships is a real Contacts block the tool can
read, edit and add to — rather than markup only the app could produce.

Three mistakes worth recording, all the same mistake:

- Cutting code between two distant anchors removed `SOCIAL_ICON_PATHS`,
  the divider helpers and `_insert_layout_chunks` along with the intended
  block; the app would not boot. The same slice in the page template took
  `tool_corner_select`/`tool_shadow_select` with it.
- An edit aimed at the cell normaliser landed in the section builder,
  because after earlier edits both matched the same indented text. A
  Columns section's stored JSON mentions every marker its cells contain,
  so the whole blob was read as one contacts block and came back
  double-escaped.
- **Edit by unique markers, verify which function you actually changed.**
  Both were caught by running it, not by reading it.

And the reason a footer block was still not editable: every template
writes its footer columns as bare strings, and a bare string normalises
to Text — so the block was escaped as plain text before anything could
recognise it. What a cell HOLDS decides what it is, and that has to be
decided before display_content is worked out.

Verified: 79 pages across all 16 templates render in both views with no
failures; the footer's block offers its rows prefilled, and the visitor
gets a working mailto: and instagram link with the footer's prose intact.

## 2026-08-25 — Contact Info became a tool, and what that turned up

Ten of the sixteen templates render a `cms-contact-tool` block and the
editor has always labelled it "Contact Info", so it presented itself as a
tool. It was not one: `_contact_tool_html()` was called from exactly one
place, `_apply_footer_layout`, so the only way to get one was to activate
a template that shipped it. `inline-editor.css` even styled a
`.cms-contact-tool-form` that nothing emitted — the form had been
anticipated and never built.

It is a tool now: in the menu under Forms, dropping with an empty block
that says what to do, and carrying its own form of eleven typed fields
(phone, email, website, address, and seven social links) with a tooltip
and a hint on each, applying on change like every other tool. Per
"Content tools", a tile plus markup would have been an Embed in
disguise; the form is what makes it a real tool.

`read_contact_tool()` is the exact inverse of `_contact_tool_html()`,
because the block IS the storage — the phone number lives in the markup
and there is no second copy for a form to read. Verified both ways:
dropped, filled in, read back with every field intact.

**What the work turned up, and nearly broke.** Testing the reader against
the shipped templates recovered *nothing* from any of the 21 blocks — and
that was correct. Those blocks are hand-written lines inside a contact
wrapper:

    <div class="cms-contact-tool"><p>Ashgrove Hair, 14 Ashgrove Road</p>
    <p>Tuesday to Saturday</p>...

They were never tool instances; the marker class matched and the label
followed. Had the form been offered on them, the first save would have
replaced a salon's name and opening hours with four empty inputs, because
the tool has no field for either. `is_contact_tool_block()` now tells the
two apart — structured items or the empty starter are the tool, prose in
a wrapper is prose — and the shipped blocks keep exactly the text editing
they already had.

The general shape worth keeping: **a marker class is not proof of
authorship.** Before offering a structured editor for a block, check that
the block was actually built by the thing that would now rewrite it.

## 2026-08-25 — A template is a complete thing, or it is not a template

Started as "templates must be exactly the same when the service is run on
a new host" and turned into the discovery that a template was never
actually a whole object.

Every template's pictures lived in one shared app folder,
`app/static/img/templates/`, and no package carried any media at all. So
exporting a template produced a zip with its words and its CSS and none
of its photographs, and the only reason importing it looked right was
that the receiving install happened to ship the same folder. The 75
pictures now live in their own package's `media/`, named
`<slug>-<what it is>.png` so a file copied into any shared place still
says whose it is. Renaming 17 of them (`hair-` for hair-salon,
`selfhelp-` for self-help) needed the migration to know both spellings.

Export was worse than incomplete, it was misleading: **1.3KB**, theme.css
and nothing else. No pages, no pictures, and none of the eleven keys only
the package declares, so a template arrived elsewhere wearing the right
colours in the wrong shape under somebody else's name. Import was
throwing the package away — unpacked to a temp dir, read once, deleted in
a `finally` — so an imported template could never be activated with its
content again. Both fixed; the same export is now 14MB and a round trip
between two hosts reproduces the template.

Shipped templates now travel as one `.zip` each, built from the source
folders by a `packager` stage in the Dockerfile and installed through the
**same extractor and installer an admin's upload goes through**. That is
the part worth keeping: the import path used to run only when somebody
uploaded something, which is exactly how it came to discard pages and
pictures for months unnoticed. It now runs sixteen times on every boot,
so a break in it is a failed start rather than a surprise later. The zips
are deterministic (fixed entry times, sorted entries), each carries an
`install.json` saying what it will install, and a reinstall is skipped
when the unpacked copy matches by hash — a repeat boot costs 0.05s, while
a template with no `templates` row is always reinstalled, which is how a
deleted builtin comes back.

Two bugs surfaced on the way, both invisible until something forced the
path to run:

- Activating a template applied its layout **before** writing its pages,
  and a header menu is built from the pages that exist — so a four-page
  bakery activated with a menu that said "Home" and nothing else.
- `shutil.copytree` carries file *and directory* metadata, so
  reinstalling a template over its own earlier copy died with "Operation
  not permitted" when the existing files belonged to another user. Copies
  now carry contents only, which is all that was ever wanted from a
  temporary extraction.

Verified on two independent fresh hosts: 16 templates activated through
the real route, 79 pages, 75 pictures, **0 missing**, byte-identical once
row ids and the per-request captcha are folded out.

Importing a template you already have is now a question with three
answers — Overwrite, Keep both, Cancel — rather than silently adding
`bakery-2`. A builtin cannot be overwritten and says so instead of
appearing to: its package ships in the image and is reinstalled every
boot, so an overwrite would hold until the next restart and then vanish.

## 2026-08-25 — The line between a tool's controls and the site's content

One boundary, stated by the owner and worth writing down: **the parts of
a tool that offer controls and options are this app talking, and are
styled centrally and identically everywhere; the content inside the tool
belongs to the site and keeps following its palette, fonts and
Corners/Depth.** Everything below follows from applying it and measuring.

A visitor was being sent the editor's half — ten `data-save-url`
attributes, twelve `/admin/sections/N/` endpoints and every row id, in
the signed-out page, for a script that is not even loaded unless an admin
is editing. Now zero. What the *page* renders with (`data-layout-width`,
`data-corner-style`, `data-shadow-style`) stays in both views, because
those style the site rather than the editor.

The controls were wearing the site's clothes, and it made them
unreadable. A section dimmed for a photograph sets `p { color: #fff }`
for the text standing on the photograph; the Numbers tool's hint is a `p`
inside that same section, so the panel explained itself in **white on
light grey at 1.08:1**. The words were there — a rule that had nothing to
do with them made them invisible. Worst case across an open panel is now
6.99:1.

The font was the same failure one layer down: `inline-editor.css` never
set one, so chrome inherited the *site's* face (Mukta on the bakery,
Inter on the CV) while the selects and buttons beside it, which inherit
nothing by default, fell back to the browser's Arial. Two typefaces in
one panel and a different pair per template. `--cms-ui-font` names the
editor's own; all **1832 controls** now resolve to it while the content
beside them still reads in the site's face.

A control does not stop being a control when it stands somewhere else:
the Rows stepper on a Columns cell sits in a bare inline form and was
reading in the site's typeface while the identical stepper inside a panel
read in the editor's. Forms a *visitor* fills in — the newsletter
sign-up, the contact form — are deliberately untouched.

There was also no convention for where a tool's name sits, and the
absence was invisible until two screenshots sat side by side. The header
is a wrapping row of two items, so the name went left or on top depending
on whether the controls happened to fit beside it — the **same** Accordion
bar put its name on the left at 400px and on top at 360px, so a tool
changed shape when its column was resized. Left could never be the rule
(four caption rows have no room beside a label in a column), so the name
now takes its own line, always.

Last, the admin screens and the dock painted their own buttons, focus
rings and selected states in whatever colour the active template used.
That is not merely inconsistent: self-help ships `#7c8c74`, which gave
the admin's primary buttons **3.58:1** for their white text, and an owner
can override the palette to anything — so the readability of this app's
own controls was decided by somebody's brand. `--cms-ui-accent` replaces
all 31 uses; self-help's button goes to 5.17:1 and the admin renders
identically whichever template is active, while the live page's dock is
the app's blue against a site `--primary` of bakery brown.

**The rule to keep**: before styling anything in the editor, ask whether
a visitor could ever see it. If not, it is the app's, and it takes the
app's colours and the app's font — never `var(--primary)`, never the
inherited site face.

## 2026-08-25 — A generated password that opened nothing

Worth recording because nothing reported it and nothing would have: it
only bites a first boot, and the person it bites cannot get in to
complain.

The image runs two workers. On a first boot both start against an empty
database, both find no admin, and both generate a password. Exactly one
becomes the admin's — the row is written once and the UNIQUE username
turns every later attempt into a no-op — but the loser was still writing
*its* password to `data/initial-admin-password.txt` and to the container
log. Whichever worker wrote last decided the file, so a fresh install
could hand the owner a printed password that opens nothing.

Found by checking rather than by symptom: `check_password_hash` of the
printed password against the stored row returned `False` on a fresh host.
The fix is that the INSERT decides who announces, not the SELECT that ran
before it — `rowcount` is the one answer that comes after the write.
Three fresh installs since: printed password opens the account, 3/3.

The general shape: when more than one worker races to seed something, the
announcement has to be made by whoever actually won, not by everyone who
thought they had.

## 2026-08-25 — Still open after the packaging and chrome work

Small, real, and deliberately not done:

- **One renderer per tool.** ~~28 of 29.~~ **CLOSED as a task**: the
  measurement is now 30 tools, 0 differences (`tools/parity_check.py`),
  and CLAUDE.md records that this has no observable payoff left. The
  structural note below stands -- there are still two renderers -- but
  nothing is owed. Still two — the section chain and
  `render_cell` — so a change to how a tool edits has to be made twice.
  Text, Image and Media Player are one macro each, the Embed's code
  editor is one pair of macros, the Basket is recognised in a cell at
  last, and every tool takes its NAME from one computation rather than
  twenty-two literals. Measured rather than estimated (see the 2026-08-25
  entries): **28 of 29 tools now offer identical controls in both
  places**, and the remaining line is one macro in two states, not a
  difference. What is left of this item is not control parity but the
  structure underneath it -- see the phases below. `tools/` holds a render
  check that hashes every tool as a section *and* as a cell, in both
  views, which is the safety
  net for finishing it — and it only became one on 2026-08-25, when its
  block regex stopped skipping every tool that carries an extra class.
- ~~This install's own leftovers~~ -- cleared 2026-08-26, with a backup
  taken first. The `/faq` page went through the app's own delete route
  rather than a DELETE, because that route regenerates every Menu
  site-wide: 21 links pointed at it. Nine orphan theme directories went
  with it (14.3 MB), leaving seventeen, every one of them in the
  library.
- **Tool unification beyond one renderer.** Phase 1 is one renderer;
  after it, phases worth scoping separately: one set of controls per tool
  (rather than a section copy and a cell copy), collapsing the pairs of
  routes that exist only because a cell needs its own endpoint, and
  finally sections becoming pure containers with no type of their own.
  Controls turned out to be done already -- every tool's panel is one
  `*_config_fields` macro called from both places. **Route pairs: 32 of
  33 collapsed** (2026-08-26). The one left is the generic `update`, and
  deliberately: unlike the other thirty-two it is not two copies of one
  thing, it is two different field sets sharing a name -- a section
  writes its own columns, including the page-level background and border
  that a cell has no notion of, while a cell writes dict keys and has a
  tool-level corner where a section has both its own and its tool's.
  Forcing those together would make both harder to read. What remains of
  this item after that is phase 4, sections becoming pure containers with
  no type of their own -- at which point `update` collapses on its own.
  **The markup half is done** (2026-08-26, "One list of tool controls"):
  the nineteen config forms are one macro called from both chains. And
  the schema half is **closed as unnecessary** -- see "Thirty tools, both
  containers, no differences": `tools/parity_check.py` shows every tool
  offering identical controls in both places, so the only thing
  `sections.type` still costs is that a section calls its tool's corner
  `tool_corner_style` where a cell calls it `corner_style`. That is a
  field name, not a behaviour. If it is ever done, it should be for a
  reason that turns up later, not for this one.


## 2026-08-23 — Install the site as an app (parked: probably not worth it)

Asked for, then parked the same day — "maybe not worth it". Not rejected
on principle; the case for it just never got strong enough to pay for
what it costs. Written up so the next session can pick it up or drop it
without working through the same ground again.

Asked for: a click-to-install control so a visitor can add the site to
their phone's home screen and open it like an app.

What it needs, and the honest asymmetry between the two platforms:

- A **web app manifest** (name, icons at 192/512, theme colour, display
  `standalone`, start URL) and a **service worker**, however trivial —
  Chrome will not offer installation without one registered.
- **Android/Chrome**: fires `beforeinstallprompt`, which can be captured
  and replayed from a button. A real one-click install.
- **iOS/Safari**: has no install API at all. Add to Home Screen is a
  manual Share-sheet action, so the most a button can do there is *show
  the instructions*, ideally with the share icon drawn so it is
  recognisable. Anything promising one-click install on iOS is lying.
- The button should therefore hide itself when the site is already
  installed (`display-mode: standalone`) and when the browser has neither
  path, rather than sitting there doing nothing.
- Icons: generate from the site's existing favicon so it is not another
  upload to explain.

Scope it as a **tool** (per "Features are tools, never page types") —
dropped where the owner wants it, most likely a footer or an About page —
plus site-level plumbing for the manifest and worker, which are one per
site rather than one per placement.

### Generating a shareable APK instead — assessed, advised against

Also asked: could the backend build an APK on click, for the owner to
share? It is possible, and these are the reasons it was not done.

- **Cost to every install.** The image is `python:3.12-slim`, 734MB, with
  no Java at all. A minimal patch-and-sign chain (headless JRE +
  `apksigner` + `zipalign`) adds roughly 300MB; a real Bubblewrap/TWA
  build (Android SDK, `android.jar`, Node) puts it past 2GB. Every
  deployment pays that, including the ones that never press the button.
- **It changes what a breach means.** Signing an APK puts a code-signing
  key on the web server. Today a breach costs data, which this project
  has explicitly accepted ("our data is not so secret"). A signing key is
  a different category: an attacker could ship an APK *signed as the
  owner*, from the owner's own site, which customers install and trust.
  The site stops being a thing that leaks and becomes a thing that
  distributes software. That is the one secret on the box worth refusing.
- **It buys less than it looks like.** A WebView wrapper shows the same
  website, so against a PWA the gain is a launcher icon on Android —
  which the PWA already provides. Sideloading needs "install unknown
  apps" and shows warnings, Play Protect flags wrapper APKs, Play itself
  rejects them under the minimum-functionality policy, iOS has no
  sideloading at all, and an APK does not auto-update while a PWA is
  always current.
- **The one real reason** to want an APK is a Google Play listing. That
  needs a developer account, a key kept off the server, and a review — a
  one-off task for the owner, not something a CMS does on click.

**If it is ever picked up**, the middle path is the one to build: a
button that generates a ready-to-build Bubblewrap/TWA project as a zip
(manifest, icons, asset-links and config filled in from the site), which
the owner builds and signs on their own machine. No Android SDK in the
image, no signing key on the server, and it is the honest route to Play.

## 2026-08-22 — Emailed links have to work on someone else's device

Found immediately after sending the first real order email: it contained
`http://localhost:5000/my/...`, which is dead on every device except the
one that generated it.

`url_for(_external=True)` builds from whichever host the CURRENT request
arrived on. For a buyer completing checkout that is right — they are on
the site. But an admin pressing Resend while working on localhost bakes
"localhost" into a link someone else opens on a phone, and the failure is
invisible until they try.

- New **Site address** setting (Email Settings): the address links are
  built from, winning over the request host whenever it is set. Verified
  by generating a link while browsing localhost and getting the LAN
  address back.
- Set to the host's own name on this install, which is how the site is
  reached across the local network. (Deliberately not written down here:
  these notes travel with the repository, and the address of somebody's
  machine is not part of the design.)

The general shape is worth remembering: anything a person will open
somewhere else — an email, a QR code, a printed URL — must not be built
from the address of whoever happened to trigger it.

## 2026-08-22 — Booking a session against a credit

The thing the whole design was for: a package of sessions, bought once,
spent one at a time against a real calendar. No off-the-shelf booking
product does this, because a package is a balance that must survive
across visits and be checked at the moment of booking.

**Done:**
- The buyer's page lists **real free times from Cal.com** for the meeting
  their sessions are for — 146 slots across five days on the live
  account. We never compute availability, timezones, buffers or clashes;
  Cal.com already knows all of it.
- Clicking a time **spends one session and books it**. Cal.com sends the
  confirmation and the joining link, as it would for any booking.
- **The credit is taken before the booking is attempted, and handed back
  if Cal.com refuses.** Booking first would leave a window in which two
  tabs could each book against the same last session.
- **`spend_credit` is atomic**: the `used < granted` test lives in the
  UPDATE's WHERE clause, so two requests racing for the last session
  cannot both win — SQL decides, not a read followed by a write.
  Verified: twenty attempts against ten sessions leave `used = 10`.
- An entitlement cannot be spent by anyone but its owner (the customer id
  is part of the same WHERE clause).
- Times are shown in the **visitor's own timezone**: the page reloads once
  with the zone the browser reports, and every booking form carries it, so
  the slot booked is the one that was clicked.

**Still to confirm:** a real booking landing in the live Cal.com calendar
— deliberately left for the owner to do by clicking a time, rather than
this session creating an appointment in someone's real diary.

## 2026-08-22 — Getting the buyer back in: link, actions, resend

**Done:**
- **The thank-you page now carries the buyer's link itself**, with
  "Book your N sessions" or "Download now" depending on what they
  actually bought, and the raw URL printed as well as linked. Belt and
  braces on purpose: a mistyped address, a slow mail server or a spam
  folder would otherwise leave someone who has just paid with no route to
  what they bought.
- **Orders screen** (`/admin/commerce/orders`) — every sale, the buyer's
  email, and what each entitlement has left. This answers the two
  questions an owner actually asks after a sale: "what has this person
  paid for" and "they say they never got their email".
- **Resend** on each order, minting a fresh link. The old one keeps
  working until it expires, which is the kind behaviour when someone may
  still have the first email. The stored hash cannot be turned back into
  a link, so resending always means issuing a new one — worth knowing
  rather than being surprised by two valid links.
- Verified end to end with a real send through the site's own Gmail SMTP:
  order email delivered, both tokens valid, orders screen listing the
  sale with its ten remaining sessions.

## 2026-08-22 — Email settings: a placeholder that looked like a value

Found while checking whether order emails could send. Every email field
was filled in except `smtp_host`, so `mailer.is_configured()` was False
and both contact messages and order emails were being **silently
skipped** — while the settings page looked completely configured.

The cause was a `placeholder="smtp.gmail.com"` on the host field. Greyed
placeholder text reads exactly like a filled-in value, and the page's own
setup instructions are written for Gmail anyway.

- **`smtp.gmail.com`, port 587 and TLS are now real defaults**, returned
  by `get_email_settings` rather than suggested by placeholder text. The
  hint below the field explains how to change it for another provider.
- **Saving an incomplete configuration now says so**, naming the missing
  fields, instead of flashing the same "saved" as a working one. The page
  also states plainly at the top whether the site can send mail.

Worth generalising: a placeholder is not a default, and any field where
the two are confusable is a field where someone will save a
half-configuration and never find out. The Integrations panel avoids this
by stating connection state in words; this page now does the same.

## 2026-08-22 — Phase two: the buyer's own page, and a Buy-button bug

**Done:**
- **A page a buyer reaches with no account**, at `/my/<token>`, showing
  their sessions to book, downloads and past orders. The token in the URL
  is the whole credential — which is why only its SHA-256 hash is stored,
  so a stolen copy of the database opens nobody's page. Reusable until it
  expires (30 days) rather than single-use: this is someone's way back to
  sessions they may spend over months, and a link that died on first
  click would strand them. An unknown token says only that the link no
  longer works — never whose it was.
- **One transactional email of our own**, sent when an order is first
  recorded, carrying that link. Stripe's receipt cannot carry it, so
  without this a buyer of ten sessions would have no route back to them.
  Best-effort by design: the order is already paid and recorded before
  this runs, so a sulking mail server must never turn a completed
  purchase into an error.
- `mailer.py` gained a general `send()`, with the contact form now using
  it — rather than a second copy of the SMTP block.

**Fixed: the Buy button's card style rendered as a bare button.**
Reported from use, and the markup showed why: the card saved correctly
but with an empty name and price, so it drew an empty box around a
button. The name and price were carried in hidden fields filled by JS on
the dropdown's `change` event — but that select also has an inline
`onchange` that submits the form, and **inline handlers run before
listeners added later**, so the form posted before the fields were
filled. Now resolved server-side from the Stripe catalogue at save time:
no race, no JavaScript, and a card always shows what Stripe currently
charges instead of a copy that can go stale.

## 2026-08-22 — Phase one proven: a real payment became bookable credits

A test-card purchase on the live (test-mode) Stripe account produced,
with no webhook configured anywhere:

    fulfilment rule   price_1U7KAa...  ->  10 credits, event type 6772046
    customer          <buyer email>, taken from Stripe, lower-cased
    order             cs_test_a1p5Jo...  1.00 CHF  paid
    entitlement       10 granted, 0 used, no expiry
    balance           10 bookable sessions

What that actually proves, beyond "a payment worked":
- **The order recorded itself with no public address.** The thank-you
  page looked the session up and wrote it, exactly as designed when the
  tunnel turned out not to be available.
- **Stripe never said "10 sessions".** It reported a paid session for a
  price id; the fulfilment rule made that ten credits against a specific
  calendar. That indirection is the whole point of the rules table.
- **No account exists for the buyer**, yet the ledger knows precisely
  what they are owed.

**Fixed along the way:** `stripe_checkout_session` hardcoded
`mode: "payment"`, which Stripe rejects outright for a recurring price —
a visitor would have hit a dead end with no explanation. The mode is now
read from the price itself, and `customer_creation` is only sent in
payment mode, where it is valid. Found because the Buy button's dropdown
label spells out "0.01 CHF / month": without the price and interval in
the label, a recurring price would have looked identical to a one-time
one and been picked by mistake.

**Named, not built:** subscriptions are now half-supported. Checkout
works, but fulfilment has no concept of recurring delivery — a monthly
price granting 10 sessions grants them once, at the first payment, not
every month. Memberships would need renewal webhooks and topping-up
credits: a real feature, not a tweak.

## 2026-08-22 — Fulfilment rules: what each product delivers

**Done:**
- **The screen that connects the two catalogues.** Stripe knows a price
  exists and that someone paid it; it has no idea "10 Coaching Sessions"
  should become ten bookings against a particular calendar. This is where
  the owner says so, once, after which the payment handler needs no
  special case per product.
- Reads the real Stripe catalogue on one side and the real Cal.com event
  types on the other, both as dropdowns — **no identifier is typed
  anywhere in this system**, on either side.
- Written as one question — "When someone buys this…" — with only the
  fields that answer needs. The alternative, every field on screen at
  once, asks the owner to understand the data model before they can sell
  anything.
- "Just take the payment" is expressed by having *no rule at all* rather
  than a rule of kind "nothing", so the handler simply finds nothing to
  grant. One less state to reason about.
- Credit expiry lives here too, defaulting to **Never** with 6/12/24
  months offered. Someone who paid for ten sessions has paid for ten
  sessions; expiry is the owner's deliberate choice, not a default.
  Applies to sessions bought from then on, never retroactively.
- File downloads are deliberately **not** offered yet: the private file
  store does not exist until the digital phase, and offering an outcome
  that grants an entitlement pointing at nothing would be worse than the
  gap.

**Next:** a real test-card purchase end to end — order, customer, credits
— then the buyer's own page and the booking flow that spends them.

## 2026-08-22 — Orders without a webhook: pull as well as push

The site has no public address while it runs locally, so Stripe cannot
deliver a webhook to it. Rather than block on a tunnel, the truth is
pulled from Stripe instead of waiting to be pushed — and that turns out
to be something the product needs permanently, not a development
workaround: a push can always be missed (endpoint down, mid-deploy,
misconfigured), and every commerce system needs an answer for that day.

**Done:**
- **Three paths now write an order**, all funnelling through the same
  `record_checkout`, which is keyed on the Stripe session id and
  therefore safe to run twice:
  - the signed webhook (once a public address exists),
  - **the thank-you page**, which records the buyer's own order as they
    land on it — this alone covers the ordinary case with no webhook at
    all,
  - **`reconcile_stripe`**, pulling recent checkouts on demand, exposed
    as "Sync orders from Stripe" in the Integrations panel.
- **One-click webhook creation over the API** for when there is a public
  URL: Stripe reveals a signing secret exactly once, at creation, so
  doing it through the API removes the copy-paste step that otherwise
  produces webhooks failing verification for no visible reason. An
  endpoint already pointing at the same URL is reused, never duplicated.
- Verified live: sync read one checkout session from the real account and
  correctly recorded nothing, because that session was never paid.

**Consequence worth keeping:** no Stripe CLI and no tunnel are needed to
develop or even to run a small shop. A webhook makes order recording
immediate and covers the buyer who closes the tab; it is no longer the
thing everything waits on.

## 2026-08-22 — Commerce phase one: Buy button and hosted checkout

**Done:**
- **Buy Button tool.** The admin picks from a dropdown of their real
  Stripe catalogue — no identifier is ever typed, and neither is a price:
  a card shows Stripe's own name and amount, so it cannot drift from what
  will actually be charged. Two styles (button, or card with name and
  price). Works as a section and in a Columns cell.
- **The markup carries only a price id, never an amount.** An amount in
  the page is a number a visitor can edit before it is charged; Stripe
  stays the sole authority on what anything costs.
- `/checkout` creates the Checkout Session server-side and redirects;
  `/checkout/thanks` looks the session up and *reports* it, including an
  honest "payment received, just confirming it" when the webhook has not
  landed yet. It never records anything itself.
- Stripe Tax is requested and silently dropped on a retry if the account
  has not enabled it — a shop that cannot sell would be worse than one
  that has to put tax in the price.
- The catalogue is cached for 60s so opening the editor does not cost a
  round trip to Stripe on every page render.
- Verified against the real test-mode account: catalogue read (one
  product), a genuine `cs_test_...` Checkout Session created, config form
  listing the real product, and `/checkout` still returning 403 without
  an Origin header — the webhook's CSRF exemption did not leak.

**Next:** the fulfilment-rules admin screen (which Stripe price grants
what), then a real test-card payment end to end once the webhook secret
is in.

## 2026-08-22 — Commerce phase one: the webhook and the ledger

**Done:**
- **The commerce schema**: `customers`, `orders`, `entitlements`,
  `fulfilment_rules`, `webhook_events`. Stripe owns money and the payer's
  details; this side owns what the payer is *owed*. There are no accounts
  — `customers` is a ledger key (the email Stripe collected), not a login.
- **`fulfilment_rules` is the piece that makes it work**: what a given
  Stripe price actually delivers. Stripe knows a price was paid; it has
  no idea "10 Coaching Sessions" should become ten bookable credits.
  Without it the webhook would need a special case per product.
- **The Stripe webhook**, and it is the only thing that creates an order.
  The browser returning to the thank-you page is never proof: a visitor
  can arrive there without paying, and a payer can close the tab.
- **Its CSRF exemption is an explicit allowlist**, not a hole.
  `SIGNATURE_VERIFIED_ENDPOINTS` in csrf.py names the one endpoint, with
  a comment saying why and what replaces the protection — Stripe is not a
  browser, sends no Origin, and proves itself by signature instead, which
  is verified before a single field of the payload is read.
- Signature check uses `hmac.compare_digest` (not `==`) so a wrong
  signature cannot be found one character at a time by timing, and
  enforces Stripe's five-minute timestamp tolerance against replay.
- **Idempotent at two layers**: the event id is recorded and repeats are
  dropped, and `orders.provider_ref` is UNIQUE so even a fresh event id
  for a session already seen cannot write a second order.
- Refunds revoke only the *unused* portion of an entitlement — sessions
  already taken happened, and pretending otherwise would put the ledger
  at odds with the calendar.

Verified with locally forged signatures (Stripe's scheme is plain HMAC,
so the whole path is testable with no Stripe account): missing, wrong-
secret, stale and tampered payloads are all rejected 400 with nothing
recorded; a genuine event books the order, grants 10 credits and 1
download, and decrements stock; replays change nothing; a refund leaves
already-used sessions used.

**Next:** the Buy button tool and a real test-mode payment end to end.

## 2026-08-22 — Commerce phase one: the Integrations panel

**Done:**
- **One panel, one registry** (`services/integrations.py`) rather than a
  settings page per provider. Every provider is the same shape — name,
  credentials, capabilities — so a tool asks `providers_with("payments")`
  instead of naming Stripe, and adding a provider later is a registry
  entry plus a client function, not another admin screen. Same reasoning
  that made the AI provider pluggable instead of hardcoding Open WebUI.
- Credentials encrypted through the existing `crypto.py` and stored in
  the settings table as `integration_<provider>_<field>`. **A blank
  secret on save means "keep the stored one"** — otherwise editing an
  unrelated field would wipe a key the admin can never read back to
  retype.
- **Live/test mode is derived from the Stripe key's own prefix**, not a
  separate toggle. A toggle is just a way for the badge and the actual
  charge to disagree; the panel says "LIVE — real money" or "Test mode"
  based on what the key itself is.
- **Test connection reads something the admin recognises** — their own
  Stripe products, their own Cal.com event types — so a pass proves the
  key reaches the right *account*, not merely that it is well formed.
  Verified live: it returned the real three event types.
- Both Cal.com traps from the previous entry are handled in the client:
  browser user-agent (Cloudflare) and per-endpoint `cal-api-version`.

**Next in phase one:** the Stripe webhook endpoint (signed, idempotent,
with its documented CSRF exemption), then a Buy button that completes a
real test payment end to end.

## 2026-08-22 — Commerce and booking: verified before building

Full reasoning in the scope brief; these are the facts that were checked
against live systems rather than assumed, because each one would have
changed the design if it had gone the other way.

- **Cal.com: a personal API key is enough.** Verified against the real
  account: `/me`, `/event-types` and `/slots` all answer with a plain
  `Bearer cal_live_...`. Three event types and 66 real slots came back.
  The paid OAuth/Platform tier is for *managed users* — building a
  service that manages OTHER people's Cal.com accounts — which is not
  our shape: one site owner, one key, their own calendar.
- **Two traps when calling that API**, neither obvious from the error:
  - `api.cal.com` is behind Cloudflare, which rejects Python's default
    user-agent with `403 error code 1010` before the request reaches the
    API at all. Reads exactly like an auth failure. Send a browser UA.
  - **Every endpoint pins its own `cal-api-version`**: `/event-types`
    wants `2024-06-14`, `/slots` `2024-09-04`, `/bookings` `2026-02-25`.
    The wrong version returns `404 Cannot GET /v2/event-types`, which
    reads as a wrong path rather than a wrong header.
- **Stripe has no inventory.** Products and Prices are a pricing
  catalogue; there is no stock field. Stock has to live here.
- **The redirect after checkout is not proof of payment** — the
  `checkout.session.completed` webhook is. Which means the webhook
  endpoint needs a documented CSRF exemption (Stripe sends no Origin
  header) where signature verification replaces the origin check.
- **`app/static/uploads` is publicly served**, so it cannot hold paid
  digital goods. Those need storage outside the web root with signed,
  entitlement-bound, expiring links.
- **Cal.com cannot be bundled into our Docker package**: on the
  self-hosted community edition, API key creation is an Enterprise
  feature — so the free bundle would be the one build that cannot do
  the session-package flow. We point at whichever instance the owner
  has instead, with an optional compose profile for self-hosters.

Decisions taken: services first, then digital, then physical. Guest
checkout only (no passwords) but a real customer record keyed on the
email Stripe collects. Credits do not expire unless enabled, default
term 12 months; the owner can grant credits with no sale. Stripe Tax
computes VAT.

## 2026-08-22 — Tool expansion, phase one: FAQ

Following the template-library audit (six templates, one skeleton; nine
standard marketing sections with no tool behind them), tools come before
templates — a template built now would need rebuilding once the tools
land. First of the nine.

**Done:**
- **FAQ tool.** Question and answer rows, three styles (divided list,
  separated cards, plain), an optional "one open at a time", and a 1-15
  stepper. Works as a full-width section and in a Columns cell.
- Built on native `<details>`/`<summary>`, so open/close, keyboard
  support and screen-reader semantics are the browser's rather than ours
  — no JavaScript at all. "One at a time" is the `name` attribute doing
  the work, not an event handler.
- **The group name is per block, not a constant.** Caught on screen, not
  in the tests: `<details name=...>` makes *everything* sharing that name
  mutually exclusive, so two FAQ sections on one page behaved as a single
  accordion — opening a question in the second silently closed one in the
  first. Each block now gets its own generated name.
- The answer field is a plain-text box on purpose. This tool must never
  become a place where an admin types markup to get a paragraph.

**Remaining in phase one** (from the audit, in the order they unblock the
most): pricing tiers, testimonial/quote, stat/metric, logo cloud, team
grid, process timeline, call-to-action band, newsletter capture.

## 2026-08-22 — Every template's Media page has its own footage

**Done:**
- **18 clips, three per template**, each a scene from that template's own
  world: the roaster drum / portafilter / latte pour for Coffee Shop,
  mower stripes / planting / leaf-raking for Family Business, and so on.
  All 10.04s at 832x480, wired into each Media page's gallery as uploaded
  clips (the capability added earlier the same day), with captions.
- The markup is built by the app's own `build_video_gallery`, so what
  ships is byte-identical to what an admin editing that gallery would
  produce — no hand-written markup in the packages.
- **Big Buck Bunny is now completely gone from the repo**, along with the
  bundled `yt-aqz-KE-bpKQ.jpg` thumbnail that existed only to serve it,
  and with it the last trace of borrowed placeholder content presented as
  a template's own work. No `data-youtube-id` and no `img.youtube.com`
  appears anywhere in shipped content.
- Re-encoded at CRF 26 before committing: 45MB -> 27MB. Raw LTX output
  varies wildly by scene entropy (rain on glass was 9.2MB, a still desk
  0.5MB), and demo content that ships in the repo AND the Docker image is
  worth compressing once rather than making every install carry it.

**Open:**
- ~~(was)~~ `cv` and `personal` still have no home-page Media Player (the other
  four do). They now have Media pages full of their own footage, so the
  question is whether a home-page clip adds anything or just repeats it.

## 2026-08-22 — Generating demo clips: ComfyUI direct, deliberately outside the app

**How the built-in templates' video content is produced** (not a feature,
and not to be turned into one — the app's own video path stays
provider-agnostic through Open WebUI, for the same reason a hardcoded
ComfyUI URL was rejected for it earlier: this codebase has to work for
installs that have never heard of ComfyUI):

- The clips shipped in `app/static/video/templates/` are rendered by
  driving the local ComfyUI HTTP API directly (`POST /prompt` with a
  workflow graph lifted from `GET /history`, swapping the positive-prompt
  node and the seeds). The script lives in the session scratchpad, NOT in
  the repo. Confirmed with the user as an authoring tool only.
- It is also simply better for a batch: ~75s per clip versus ~150s
  through Open WebUI, because no tool-calling LLM has to load, decide and
  hold VRAM alongside the video model.

**Why the Open WebUI path stopped working mid-session** (worth reading
before debugging it again):

- The LLM that decides the tool call and the video model that renders it
  share one 17.1GB card. Ollama's default ~30-minute keep-alive pins
  ~7.8GB for `qwen3-vl:8b`, and ComfyUI holds its own model after a
  render. Between them the card reached **0.1GB free**, and every
  dispatch afterwards silently did nothing — no error, just `null`.
- Freeing both (`ollama stop <model>`, `POST /free {"unload_models":
  true, "free_memory": true}`) restored 15.6GB — and the dispatches STILL
  didn't arrive, while a plain chat completion did. So there are two
  separate faults: VRAM exhaustion, and a broken tool-execution path on
  the Open WebUI side that has not worked since 15:39 local. The second
  one is server-side and outside this repo.
- Useful observability, none of it visible from this app: ComfyUI's
  `GET /queue` shows whether a request ever arrived, `GET /system_stats`
  reports real VRAM, `GET /history` holds the full graph of past renders,
  and `ollama ps` shows what is pinned in VRAM and for how long.

## 2026-08-22 — Operational notes on the video backend

Learned the hard way while generating the template clips; none of it is
visible from the code alone.

- **Never rebuild the container while a generation is running.**
  `docker compose up --build` recreates the container, which kills the
  `docker exec` running inside it. Cost a batch mid-flight.
- **A render outlives its client, but a dispatch does not.** Killing the
  client during the ~120s dispatch call appears to lose the request
  entirely (nothing was rendered). Killing it *after* dispatch does not:
  ComfyUI finishes and writes the file regardless.
- **ComfyUI writes every render to `D:\Ai\output\Video` on the host**
  (`LTX23_fp8_000NN_.mp4`), independent of Open WebUI's Files store.
  That is the authoritative copy and the recovery path — files match the
  ones this app saved byte for byte, so anything lost client-side can be
  matched back by size and timestamp.
- **The container clock runs 2 hours behind the host.** Worth knowing
  before concluding a job is stalled: a directory stamped 15:18 inside
  the container is 17:18 outside it, which briefly looked like a job
  that had produced nothing for two hours.
- Consequence for `ai_video.py`, not currently a bug but worth knowing:
  a render orphaned by a killed client lands in the Files store with no
  owner. The result is identified as "a video id that wasn't there
  before AND created since this dispatch", so an orphan created *before*
  the dispatch can't be claimed — but one that happens to finish during
  a later dispatch could be. Inherent to polling a shared store; there
  is no request id to correlate on.

## 2026-08-22 — Video Gallery takes uploaded video, not just YouTube

**Done:**
- **A gallery can hold a site's own footage.** It was YouTube-only, which
  meant a site had to publish its video to a third party before it could
  show it — and it's why the built-in templates' Media pages had to
  borrow someone else's sample clip. Each clip row now has an ⬆ upload
  button beside its link field; a clip is a YouTube link *or* an uploaded
  file, and the two mix freely in one gallery.
- An uploaded clip is its own thumbnail — no poster image to generate,
  store or keep in sync. **The `#t=0.1` on the thumbnail's `src` is
  load-bearing**: `preload="metadata"` gives the browser the dimensions
  but leaves the tile painted black, because nothing has told it to
  decode a frame. The media fragment makes it seek and paint that frame.
  Found by looking at the rendered page — every automated check passed
  while the gallery was a row of black rectangles.
- The popup player gained a video mode beside its existing iframe and
  image modes, each open hiding the others, so a YouTube player can
  never sit playing audio behind a local clip.
- The clip's stored path rides through the form as a hidden field, so an
  upload survives every later rebuild of the gallery (caption edit,
  layout change, add/remove) instead of vanishing on the next submit.
- Uploads are video-only (a gallery of audio files has nothing to show),
  extension-checked, and stored under the usual secure_filename + generated
  name rule. Works in a Columns cell as well as a full-width section.

## 2026-08-22 — Copy review of the remaining 5 templates

**Done:**
- Reviewed Family Business, Coffee Shop, CV, Personal and Self-Help
  against their own briefs (Life Coaching had its pass earlier), page
  copy and blog posts alike. **Four of the five needed nothing.** Each
  has a distinct, consistent voice carried by concrete detail rather
  than filler — Miller's folksy warmth ("if you call, one of us actually
  picks up"), Jordan Avery's opinionated brevity ("allergic to
  unnecessary meetings"), Self-Help's anti-hype stance ("no toxic
  positivity — bad weeks are allowed here"), Coffee Shop's specifics
  ("every roast is under 12kg, tasted and logged"). The blog posts are
  the strongest copy in the whole set ("I tried the 5am routine for
  exactly eleven days"; "9 steps and a 40% completion rate").
- **One real defect, in Personal's Portfolio page**: the intro read "A
  few recent favorites — masked into different shapes just to show it's
  possible; use whatever fits your own eye." That is the CMS talking to
  the admin, inside copy that ships as a real site's words — load the
  template, don't edit that page, and a visitor is told "just to show
  it's possible". Rewritten in Sam's own voice.
- The same page masked its three landscape photos into a circle, a
  hexagon and a diamond. That is a catalogue of the Image tool's shape
  feature, not a photographer's portfolio — nobody crops a coastline
  into a hexagon. All three are now the same rounded crop; the mask
  feature is still discoverable from the tool's own panel, which is
  where a feature belongs rather than in demo content.
- Added a repeatable check for this class of bug: a scan of every
  template's page and blog copy for admin-facing language ("just to
  show", "you can", "this template", "placeholder", "for example", ...).
  It now returns zero hits across all six.

## 2026-08-22 — Depth (shadow) presets

**Done:**
- **Elevation, the one visual-depth lever the app didn't have** (it had
  corner radius, fill colour and border). Built as ONE shared control on
  the Corner Style pattern — a site-wide "Depth" preset gallery in the
  Colors panel plus a per-section override in "This Section" — rather
  than separate shadow options on Image, Banner and Card, which would
  have been the same control implemented three times.
- Four presets only (Flat / Subtle / Raised / Floating). Offset, blur,
  spread and colour as separate inputs would be four ways to get one
  effect wrong, and a heavy black drop shadow is the usual amateur tell.
- **Tinted from the palette, not black**: `color-mix(... var(--primary)
  18-28%, transparent)`. Every other colour in the app flows from the
  palette, and a black shadow is *invisible* on a dark theme — a tinted
  one stays visible on either because the tint is a real hue rather than
  an absence of light.
- **A full-bleed section stays flat on purpose.** A shadow says "this
  sits above a surface", but a full-width hero IS the surface, so
  elevation there reads as a mistake. `[data-layout-width="full"]` drops
  it rather than offering a choice that always looks wrong.
- Cascade matches Corner Style exactly: theme's own default -> site-wide
  `templates.shadow_override` -> per-section `sections.shadow_style`,
  with "Reset to theme default" clearing the per-section values too so
  reset means pristine.
- `shadow_override` is carried through package export/import/save-as-
  template — the BOW records font/shape overrides being silently dropped
  on that path once before, so it was wired into all three code paths
  (install-update, install-insert, capture) in the same change.

**Notes for whoever touches this next:**
- A `theme.css` may hard-code its own `box-shadow` on a card or banner,
  and site-base.css's var-reading rule loses to it on source order — the
  coffee-shop theme does exactly that, and the first working version
  appeared to do nothing on cards because of it. Two fixes, both needed:
  the per-section rules use an attribute selector (outranks a bare class
  in any theme.css, the same trick corner_style already uses), and
  `_theme_override_css` re-emits the var-reading rule inline after the
  theme's stylesheet when a site-wide Depth is set.
- Elevation applies to Card, Banner, Image and the File tool's card.
  Deliberately not the generic `.block-html` tools — a shadow on a
  transparent table or menu block has nothing to cast against.

## 2026-08-22 — Image Accordion display styles

**Done:**
- **Carousel and Masonry displays**, alongside the original hover-expand
  Panels — a "Display" select on the tool's own config form. The three
  share the *same* panels: identical markup, identical images and
  captions, only the container's class differs
  (`cms-accordion-style-<name>`), so switching display can never lose
  content and switching back restores the original look exactly.
  Content saved before this existed carries no style class at all, which
  the CSS reads as Panels, so nothing had to be migrated.
- Carousel is a scroll-snap track: touch devices get native swiping for
  free, and prev/next buttons are injected at runtime by `site.js` (the
  same approach the mobile table wrapper uses) rather than saved into the
  section's content — so the stored markup stays identical across
  displays and no stray controls can be left behind. Buttons disable at
  each end and advance exactly one panel (snap-align is `start`, not
  `center`, which is what makes a one-panel scroll land on a snap point).
- Masonry is a 3-column stagger on a repeating 320/210/260 height cycle
  so it reads as deliberate rather than random, with captions always
  visible since there is no hover state to reveal them.
- Mobile: Panels stacks (unchanged), Masonry drops to one column,
  Carousel keeps its swipe track — a snap track is the right touch
  behavior, so it is explicitly exempt from the stacking rule. Verified
  at 375px with no horizontal page overflow.
- Documented the tool in `admin/help.html` and the assistant's system
  prompt — **it was in neither**, despite being a real tool since the
  earlier pass that built its editing form.

**Open:**
- ~~Lightbox~~ — done. It is a *behaviour*, not a fourth display: a
  "Click to enlarge" checkbox that rides on top of whichever display is
  chosen (its own `cms-accordion-lightbox` class, kept separate from the
  style class so switching display can't silently turn it off). The
  Video Gallery's existing `#cms-lightbox` overlay gained an `<img>`
  mode alongside its iframe, with each open hiding the other so a
  still-loaded player can never keep playing audio behind a photo.
  Opens on click or Enter/Space (panels are already focusable for the
  hover display's keyboard support), closes on Escape, backdrop or the
  close button, and stays out of the way in edit mode where a click
  means "configure this tool".
- ~~Cover Flow and Stack/Deck~~ — done, see the "Cover flow and a deck
  of cards" entry at the top. The original note below is what they were
  built from.
- ~~(was)~~ **Cover Flow and Stack/Deck** still need their own scoping pass (3D
  perspective, swipe-gesture handling) rather than being rushed in.
- ~~Image Accordion isn't available in a Columns cell~~ — done. A cell
  now gets the same config form as a full-width section (display style,
  click-to-enlarge, panel stepper, per-panel caption/upload/generate),
  through four cell-scoped routes. The form logic itself moved into one
  shared `apply_accordion_form()` so the section and cell routes can't
  drift, and `accordion_config_fields` now takes the state object and the
  section separately — a cell carries the accordion's state but has no id
  of its own to build URLs from.
- ~~The panel count is fixed at five~~ — done. A -/+ stepper on the
  tool's config form adds or removes a panel at the end, bounded 2-12
  (one panel isn't an accordion; past a dozen the hover display gives
  each panel a slice too thin to read). A new panel starts on the
  placeholder image with a numbered caption — the same state a brand-new
  accordion's panels start in, so there's no second "empty panel" shape
  to style. Captions are applied before the add/remove so a caption
  typed in the same submit as a "remove" still lands on the panels that
  survive. The stepper itself is now a shared control
  (`.cms-stepper`/`.cms-stepper-count`) rather than the Table tool's own
  `.cms-table-config-group`, since both tools use it.

## 2026-08-22 — Video gallery thumbnails self-hosted

**Done:**
- **A gallery no longer talks to Google on page load.** Every thumbnail
  was fetched live from `img.youtube.com` by every visitor, on every
  visit, before anyone clicked play — the same third-party exposure the
  self-hosted-fonts pass removed, and the reason the player itself
  already used youtube-nocookie. `build_video_gallery()` now pulls each
  thumbnail once at save time into the site's own uploads
  (`_local_youtube_thumbnail`) and points the markup at that copy.
  Fetches are capped (2MB, 6s, image content-type only) and cached by
  video id, so the same clip is only ever downloaded once however many
  galleries use it — a re-save of an already-seen gallery costs no
  network at all. If the fetch fails the markup falls back to the local
  placeholder rather than a remote URL: a missing picture is a smaller
  problem than quietly reinstating the request this removes.
- The filename is derived from the video id rather than randomised (the
  usual rule for uploads) precisely to get that caching. Safe here for
  the same reason the id is safe in a URL — it's matched against a strict
  11-character pattern first and is never a client-supplied filename.
- All 6 built-in templates' Media pages repointed at a bundled copy of
  the sample thumbnail (`/static/img/templates/yt-<id>.jpg`), so nothing
  in the repo carries a remote thumbnail URL either.
- Verified live: loading a Media page issues zero requests to any
  google/gstatic/youtube domain — every asset is same-origin.

**Open:**
- ~~A gallery saved before this change keeps its remote URLs~~ —
  **stale, checked 2026-08-26**: no shipped template holds a remote
  thumbnail or clip URL. Only a site that had its own gallery from
  before the change could, and that is one re-save. The original note
  follows.
- ~~(was)~~ **A gallery saved before this change keeps its remote URLs until it is
  next edited**, since the rewrite happens on save. Fine for this repo
  (the built-in packages were rewritten directly), but an existing
  install's own galleries would need a re-save, or a one-time migration.

## 2026-08-22 — Template home-page videos (and 3 real bugs in the video path)

**Done:**
- **Replaced the shared YouTube placeholder on 4 templates' home pages
  with their own generated clip.** `business`/`coaching`/`coffee-shop`/
  `self-help` each ended their home page with a Media Player pointing at
  the same `youtube.com/watch?v=aqz-KE-bpKQ` (Big Buck Bunny) under a
  real title ("How We Roast", "A Note From Me", ...) — real framing,
  placeholder content. Each now ships its own 10s 832x480 clip at
  `/static/video/templates/<slug>-home.mp4` (mirroring the existing
  `/static/img/templates/<slug>-banner.png` convention for banners) with
  the section flipped to `media_type: "video"`. The generating prompt is
  recorded as a page-level `video_prompt` — documentation only, nothing
  reads it at install time, same role `image_prompt` plays.
- **Fixed: a `null` dispatch response was read as failure.** Open WebUI
  answers `/api/chat/completions` with HTTP 200 and a body of `null`, and
  `_dispatch` treated that as "backend still waking up" — re-dispatching
  every 15s for 6 minutes, then raising. But the Tool *does* run on a
  `null` response: confirmed live, a probe that answered `null` at
  12:27:00 landed its clip in the Files store at 12:27:40. So the retry
  loop was queueing a fresh render every 15 seconds against a backend
  already rendering, then reporting failure for a video that existed —
  the source of the 25 stray clips sitting in that Files store. Now:
  dispatch once, poll regardless of what the dispatch said, and re-nudge
  exactly once if nothing has appeared by the end of the wake window (the
  genuinely-asleep case still works). A real HTTP error still fails fast
  with Open WebUI's own message rather than waiting out a 20-minute poll.
- **Fixed: every generated video was portrait.** The `comfy_media_gen`
  Tool takes `width`/`height`/`duration`/`avoid`/`upscale` and defaults
  to **256x448 portrait, 10s** — and this app never passed a size, so
  every clip it ever generated was a 256-pixel-wide phone-shaped video
  dropped into a landscape player (all 25 in the Files store are
  256x448). Saying "16:9 widescreen" in the scene description does
  nothing: the model fills the size *arguments*, not the prose. Now
  `VIDEO_SIZE_PX = (832, 480)` (services/sections.py, alongside
  BANNER_SIZE_PX/CARD_SIZE_PX) is passed through
  `generate_video(width=, height=)`, which states it in the dispatch
  prompt the tool-calling model reads. A Tool with no size argument just
  ignores it — this app still knows nothing about what's behind the Tool.
- **Fixed: a second generation could return the first one's clip.** The
  result was identified as "newest video created since dispatch", with a
  5-second grace window — but polling only starts once the dispatch call
  returns, up to 120s later, so anything that landed in between
  qualified. Caught it live: generating 4 clips back to back produced
  `business` byte-identical to `coaching` (same md5). Now the set of
  existing video file ids is snapshotted *before* dispatch and the result
  is "the id that wasn't there before" — exact, no timestamp guessing.
- Verified live: each of the 4 templates activates to a home page
  carrying a `<video>` with its own clip and no YouTube link left; all 4
  files distinct by md5; 10.04s / 832x480 / 1.0-2.0MB each, ~2min render.

**Open:**
- ~~(finding, not a task)~~ **24 seconds is not achievable on this backend** — the original ask.
  Two attempts produced nothing (the second waited a full 20-minute poll
  window) while a 4s clip renders in ~2 minutes and 10s in ~2.3, and no
  clip longer than 10.04s exists in the Files store. Reads like a frame
  count/VRAM ceiling in the ComfyUI workflow, and the failure is
  *silent* — whatever ComfyUI raises is swallowed by the `null` dispatch
  response, so this app can only report "took too long". Two follow-ups
  if longer clips matter: raise the limit in the workflow (outside this
  app), and find out whether the failed task's error is retrievable from
  Open WebUI at all (the chat is deleted in a `finally` today — it may
  hold the Tool's error message).
- ~~The `/media` page galleries still ship 3 copies of the same sample
  YouTube clip~~ — done. The gallery learned to hold uploaded video, and
  each template now shows three clips of its own.
- ~~`cv` and `personal` have no home-page Media Player~~ — **stale,
  checked 2026-08-26**: no template has one now. The redesign gave each
  of the sixteen its own home page, and none of them ends on a video.
  The original note follows.
- ~~(was)~~ **`cv` and `personal` have no home-page Media Player at all**, so they
  got nothing this pass — worth deciding whether they should have one.

## 2026-08-22 — Table + Video Gallery editing forms

**Done:**
- **Table and Video Gallery now have real editing forms** — the last two
  tools whose only way to change anything was the raw "Edit HTML" escape
  hatch (the gap Image Accordion was fixed for earlier). They're fixed
  differently on purpose, because they're different *kinds* of content:
  - **Table**: its cells are real text, already contenteditable, so its
    structure is edited straight in the live table and saved through the
    same WYSIWYG save the cell text uses (no route, no server-side
    rewrite — a rewrite could only ever act on the last *saved* text and
    would silently drop whatever was just typed into a cell). New config
    row: style dropdown (Bordered / Striped rows / Colored header /
    Plain), a Header row checkbox, and −/+ steppers for rows and columns
    with live counts. Guards stop at one row / one column. This replaces
    the old "▦ Table Style" button, which cycled blindly through four
    class names and was the tool's *only* control; that button is gone
    from the shared WYSIWYG ribbon, so there's one way to set a table's
    style, not two. A Table also loses the `</>` raw-HTML button now
    that every part of its shape has a real control.
  - **Video Gallery**: pure derived markup (thumbnail URL + data
    attribute off a YouTube id), so it's locked out of contenteditable
    and rebuilt server-side from the submitted clip list, exactly like
    the Menu tool. One form row per clip — pasted YouTube link, optional
    caption, × to remove — plus "+ Add video" (max 12) and a layout
    select (auto-fit / 2 / 3 / 4 across). New: captions render as an
    overlay across the bottom of a thumbnail, and a clip with no link
    yet is a real slot ("Add a YouTube link above") shown only while
    editing, so an admin can add three and fill them in one at a time.
    `BLOCK_LIBRARY["video-gallery"]` is now built by the same
    `build_video_gallery()` every edit goes through, so the starter and
    an edited gallery can't drift into two markup shapes — and the
    starter is empty slots rather than three copies of someone else's
    sample video.
  - Both work identically in a Columns cell (`is_table`/
    `is_video_gallery` set in `_normalize_column_cell` as well as
    `_prepare_sections`, plus per-cell routes for the gallery).
  - Also fixed while here: clicking a gallery thumbnail while editing
    opened the YouTube popup player over the top of the tool panel you
    were trying to reach. The lightbox now stays out of the way in edit
    mode (unchanged for real visitors).
  - `_youtube_id` had a second copy in `routes/public.py`; the one
    implementation now lives in `services/sections.py` where the gallery
    builder can share it (routes -> services, never the reverse).
  - Verified live: all 6 built-in templates' shipped tables and
    galleries parse to the right state and round-trip through the
    rebuild unchanged; every table control exercised in a real browser
    (top-level section AND a Columns cell, each editing only its own
    table); gallery add/remove/layout/caption verified through the real
    routes; empty slots hidden from visitors, shown while editing.

**Open:**
- ~~Video gallery thumbnails still come from `img.youtube.com`~~ — done,
  see the "Video gallery thumbnails self-hosted" entry at the top.
- ~~The 6 built-in templates' Media pages still ship three copies of the
  same sample clip~~ — **stale, checked 2026-08-26**: there is no
  `aqz-KE-bpKQ`, no `youtube.com` and no `img.youtube.com` anywhere in
  `app/data/templates/` any more. The template rebuild replaced every
  gallery with the template's own local clips and real captions. The
  original note follows.
- ~~(was)~~ **The 6 built-in templates' Media pages still ship three copies of the
  same sample clip** (`aqz-KE-bpKQ`, Big Buck Bunny) — fine as a demo of
  the look, but it's placeholder content presented as real. Worth a pass
  now that captions and layout exist to make those galleries look
  deliberate. (The home-page Media Players carrying the same placeholder
  were fixed — see the entry above — but a gallery can't take a generated
  local file, so this one is still open.)
- ~~`assistant_system_prompt.j2` still describes a "Demo Data" panel~~ —
  done. Its Dashboard section now describes the real actions (Activate /
  Load Content / Export / Delete / Import / Save current site as a new
  template, plus every template having an editable palette). Two Python
  docstrings that still explained themselves in terms of "the way Demo
  Data's Load does" and "the old DEMO_PACKS literal" were repointed at
  what actually exists; the phrase now appears nowhere in the codebase.

## 2026-08-22 — Built-in template quality pass

**Done:**
- Deleted the 6 basic theme-only shells (`simple`/`saas`/`editorial`/
  `corporate`/`dark-studio`/`warm`) — each one's identity is now fully
  absorbed into its paired content pack, which ships its own theme.css/
  palette/fonts directly. This also fixed a real bug: content packs had
  become independent template rows this session, but nothing ever copied
  a paired theme's CSS onto them, so every activated template was
  silently rendering with zero bespoke styling — the root cause of "these
  don't look well thought out."
- Gave all 6 content packs (`business`/`coaching`/`coffee-shop`/`cv`/
  `personal`/`self-help`) a genuinely distinct art direction — new
  complementary palettes, Google Font pairings, new AI-generated hero
  imagery, distinct corner/shape language per theme (sharp Bauhaus vs.
  organic bohemian vs. cottagecore-rounded, etc.). Life Coaching also got
  a copy pass (hero/about text) to match its "bohemian, not corporate"
  brief — the other 5 kept their existing copy, which didn't have the
  same tonal mismatch.
- Fixed the Contact page on all 6 templates: `page_type` was `standard`
  despite copy promising a form — now `page_type: contact`, using the
  real built-in contact-form feature.
- Fixed the Contact form's submit button rendering completely unstyled
  for real (logged-out) visitors — it borrowed an admin-only editor CSS
  class that only loads while logged in as admin, so nobody testing their
  own site while logged in would ever have noticed.
- Built the Image Accordion tool properly: it only ever had a tool tile
  and starter markup, never a real editing form, so an admin's only way
  to change its images/captions was the raw "Edit HTML" escape hatch —
  exactly what CLAUDE.md's tool-usage rule exists to prevent. It now has
  a dedicated per-panel config form (caption input + upload/generate
  buttons per panel), locked out of the generic contenteditable/raw-HTML
  fallback the same way Menu/Divider/Breadcrumb already are.
- New Fonts & Shape panel (`partials/style_panel.html`) — curated font-
  pairing and corner-radius presets, same override-on-top-of-default
  architecture as the Colors panel, so a look's typography/shape language
  is admin-adjustable without touching CSS.

**Open:**
- ~~Table and Video Gallery have the same editing gap Image Accordion
  just got fixed for~~ — done, see the "Table + Video Gallery editing
  forms" entry at the top; the reasoning below is what it was built from.) Both are real, distinct tool tiles (not the
  generic Embed escape hatch) — that part is fine — but neither has a
  dedicated config form; an admin's only way to change a table's cells or
  a video gallery's clips today is the raw HTML editor. Needs the same
  treatment: an `is_table`/`is_video_gallery` detection flag (see
  `is_divider` in `routes/public.py`'s `_prepare_sections`), a dedicated
  config-fields macro, and update route(s) — Table in particular already
  has real dedicated per-cell contenteditable + a style toggle, so it may
  only need row/column add-remove controls, not a full rebuild.
- ~~Image Accordion display-style variants~~ — Carousel and Masonry
  done, see the "Image Accordion display styles" entry at the top;
  Lightbox and Cover Flow/Stack-Deck still open there.
- ~~Review the remaining 5 templates' page copy~~ — done, see the
  "Copy review of the remaining 5 templates" entry at the top.
**Done since (these were appended to the Open list by mistake — every one
of them is finished work, written in the past tense):**
- Per-section and per-zone (header/footer/sidebar/sidebar_right/body)
  background+border color overrides, and per-section Corner Style —
  all consolidated into the Colors panel's "This Section" sub-area
  (click any section/zone, then open Colors) rather than inline page
  chrome. Both Colors' and Shape's "Reset to Theme Default" now cascade
  into matching section-level overrides too.
- Fonts panel reworked into one style-revealing ~50-font list with
  Heading/Body/Footer apply buttons (Footer is optional, defaults to
  following Body) — replacing two separate dropdowns.
- Custom-tool toolkit import/export (`app/services/tools.py`) — export
  one or all admin-created tools as a `.json` file, import only adds
  tools whose name doesn't already exist. Template Package export/save
  now bundles a site's custom tools the same way, and reading them back
  in on import uses the same skip-if-exists rule.
- Fixed: `_build_package_dir` never captured `font_overrides`/
  `shape_override`/`zone_style_overrides` — exporting or saving-as-a-
  template silently dropped any custom font/shape/zone-color choice.
  Also fixed a `shutil.SameFileError` crash in `save_current_site_as_
  package` that only surfaced once every template actually had its own
  theme.css (see the "not well thought out" fix above) — untested since
  then.
- Fixed: deleting a page left it as a dead link in any Menu tool section
  that included it (a Menu's link list is baked HTML, never re-resolved
  against the pages table on render) — `page_delete` now regenerates
  every Menu section site-wide.
- Normalized tool config panel control sizing (Banner and others) —
  native select/button/input elements had no shared height/box-sizing,
  so a config row never quite lined up.
- Breadcrumb tool actually used now (Life Coaching/CV/Personal's About
  pages, one of each of its 3 styles) — was built earlier this session
  but never used anywhere in the demo content. Found and fixed a real
  legibility bug doing this: `.cms-breadcrumb`'s text color was a fixed
  `#666`, unreadable on a dark theme's background.
- **AI video generation, wired through Open WebUI only.** The earlier
  `/api/v1/videos/generations` path (405, dead end) is abandoned — but so
  is a first attempt at wiring `app/ai_video.py` directly to a specific
  self-hosted ComfyUI URL, which the user correctly rejected: this app is
  meant to be installable by other people, and a hardcoded link to one
  person's own GPU box doesn't generalize the way "Open WebUI is the
  pluggable AI provider" already does for chat and images. Corrected
  design: a new "Video Generation Model" field on AI Settings (Open
  WebUI only, mirrors `openwebui_image_model`) names a model/persona that
  has a video-generation Tool attached in Open WebUI's own Workspace →
  Tools — this app has zero knowledge of what that Tool actually calls
  (ComfyUI, a hosted API, anything), same boundary as image generation.
  Getting this working took real reverse-engineering: Open WebUI's
  `/api/chat/completions` only ever returns the model's *decision* to
  call a Tool (`finish_reason: "tool_calls"`) — it does not execute it,
  even with `tool_ids` passed and even streaming. Real execution only
  happens when the request is tied to a live chat (`chat_id` + `id` +
  `stream: true`), which switches the response into an async task
  dispatch (`{"task_ids": [...]}`) instead of a normal completion; the
  Tool's resulting file then lands in Open WebUI's own Files store
  (`GET /api/v1/files/{id}/content`) as a side effect of the task
  running, independent of whether the chat message itself ever gets
  saved (that part is client/websocket-driven, which this app doesn't
  speak). `app/ai_video.py` resolves the configured model's tool ids via
  `/api/models`, filters them against `/api/v1/tools/` (a model's own
  `toolIds` can reference a stale/renamed tool, which silently breaks the
  whole dispatch if passed through unfiltered), dispatches, and polls
  Files for the newest video-typed entry created since. Also discovered
  live: the user's Open WebUI sits in front of a GPU box that sleeps when
  idle and wakes on demand — a dispatch attempt made before it's awake
  comes back as a bare `null` (or the connection just times out) rather
  than a real error, so dispatch retries for up to `DISPATCH_WAKE_TIMEOUT_S`
  (8 min) before giving up. Wired to a new 🎥 Generate button on any Media
  Player tool set to "Uploaded video" (top-level and Columns cells alike
  — `section_media_generate`/`section_column_media_generate`), matching
  the existing ✨ Generate pattern for images. Gunicorn's timeout raised
  120s → 2000s (Dockerfile) to cover both the wake-wait and a real render,
  since this app has no async job queue of its own — the whole request
  blocks, same as image generation just much slower.
- **Fixed: several "feature card" columns were Text cells wearing a
  Card's markup, not real Card cells.** Raised by the user from a
  screenshot of Coffee Shop's home page — those 3 cards showed the plain
  Text toolbar, not Card's (shape/image/color controls), because the
  underlying cell was a bare string containing a `cms-card-shape` div
  rather than `{"type": "card", ...}`. `_normalize_cell` treats any bare
  string as legacy Text content regardless of what HTML it contains — by
  design, but this was genuinely pre-per-cell-tool-identity leftover
  content, not something a real admin could reproduce by picking Card
  from the tray (a manually-added Card cell has always been a proper
  dict). Converted all 12 affected files (`00-home.json`/`01-about.json`
  across all 6 templates) plus Family Business's `sidebar_widget` in its
  manifest (same bug, one level up) to real `{"type": "card", ...}`
  cells. Confirmed live: Coffee Shop's home page cards now show the real
  Card config toolbar after a content reload. Conclusion for future
  content: Card-look content must always use an explicit Card cell, not
  Text with embedded markup — Text does not get a corner-style/shape
  override for this reason, Card already has its own.

**Open / blocked:**
- ~~Table and Video Gallery still need the Image Accordion editing-form
  treatment~~ — done, see the 2026-08-22 "Table + Video Gallery editing
  forms" entry at the top.
- ~~Image Accordion display-style variants~~ — Carousel and Masonry done,
  see the entry at the top.

## 2026-08-22 — Reset/removal cleanup, mobile tables, font/color depth, self-hosted fonts

**Done:**
- AI video generation reworked to go through Open WebUI only (no
  hardcoded personal ComfyUI URL — this app has to work for any
  deployment, not just the one it was built against). Added a "Video
  Generation Model" AI Setting naming a model/persona with a
  video-generation Tool attached in Open WebUI's own Workspace → Tools.
  Reverse-engineered the actual execution path: `/api/chat/completions`
  never runs a Tool from a bare call, even with `tool_ids` passed — only
  a request tied to a real chat (`chat_id` + message `id` + `stream:true`)
  switches the response into an async task dispatch, whose result lands
  in Open WebUI's own Files store (`GET /api/v1/files/{id}/content`)
  independent of the chat ever being saved. `app/ai_video.py` resolves
  the configured model's tool ids via `/api/models`, filters them against
  `/api/v1/tools/` (a model's own `toolIds` can reference a stale/deleted
  tool, which silently breaks dispatch if passed through unfiltered),
  dispatches, retries on the "backend still waking up" case (a bare
  `null`/timeout, not a real error), and polls Files for the result.
  Confirmed working once end-to-end; deprioritized per the user after —
  not worth further debugging time, and the live deployment will likely
  run Gemini as its provider anyway (no video path there).
- Removed the "+ New custom tool" admin creation form and the AI
  Assistant's `create_content_tool` capability. On inspection, a "custom
  tool" was just a saved (section_type, raw HTML) pair — using it well
  required hand-typing HTML, which is exactly the Embed-wrapped shortcut
  CLAUDE.md's "use the right tool for the job" rule exists to prevent,
  and it's structurally the *only* thing the AI could ever produce here
  (it proposes content, not code, so it can never build a genuinely new
  capability). Kept tool Delete and the Toolkit import/export system
  (`services/tools.py`) — an admin can still bring in a tool via an
  imported Template Package or a shared toolkit file, just can't hand-type
  one from scratch anymore.
- Card tool gets a "↺ Reset" button (shape/color/image back to default in
  one click) — added `card_style_settings()`/`_reset_card_style()` in
  `services/sections.py`. Fixed a real bug found while building it: the
  color swatch always showed a hardcoded `#f0f1f3` regardless of the
  card's actual saved color.
- Mobile table overflow fixed. First attempt (display:block + overflow-x
  directly on `.cms-table`) broke header/body column alignment (thead and
  tbody become independently-sized tables once split) — reverted in favor
  of wrapping the table in a `.cms-table-scroll` div at runtime
  (`site.js`), which leaves the table's own layout untouched. Skips a
  table inside a contenteditable region (edit mode) so the wrapper never
  gets captured into saved content on next save.
- Corner Style moved out of the Fonts panel into Colors (it shapes
  Banner/Card/section boxes, not text — grouping it under the 🔤 icon was
  the actual bug the user flagged). Fonts panel is just "🔤 Fonts" now.
  Also fixed a stale hint in the Colors panel still describing a "🎨
  button" on sections/zones from before that was replaced with ambient
  click-to-select earlier this session.
- WYSIWYG Text toolbar's font dropdown now includes all ~50
  `GOOGLE_FONT_CHOICES` (style-revealing, same as the Fonts panel),
  grouped under "System" / "Google Fonts" `<optgroup>`s, alongside the
  original 6 web-safe fonts.
- Color palette depth: each of the 3 role colors (primary/secondary/
  accent) now expands into a 6-step tint/shade ramp (`lightest`/`light`/
  base/`dark`/`darker`/`darkest`) via `services/palette.py`'s
  `tint_shade_ramp()`, bridged into `--{role}-{step}` CSS vars by
  `_theme_override_css` the same way `--{role}-dark` already was.
- **Self-hosted every Google Font — zero runtime requests to Google.**
  Prompted by a legal/privacy check (OFL 1.1 / Apache 2.0 both explicitly
  permit self-hosting and bundling font files with software, including
  selling it, as long as the font itself isn't sold standalone — just
  requires carrying each font's license text). Since there's no free-form
  font-name input anywhere in the app, every possible choice is a closed,
  fixed set: the 7 non-empty `FONT_PAIRINGS` presets + all 50
  `GOOGLE_FONT_CHOICES`. Downloaded the real `.woff2` files (fetched with
  a real Chrome User-Agent so Google serves clean WOFF2-only `@font-face`
  blocks, not legacy TTF+unicode-range-split fallbacks) and each family's
  OFL/Apache license text from Google's own `google/fonts` GitHub repo
  into `app/static/fonts/` (~5.8MB total, see its own README.md) — 8
  local CSS bundles (one per pairing + one shared `choices.css` covering
  every individually-pickable font, since a browser only fetches the
  specific weight/style actually used regardless of how many
  `@font-face` rules a stylesheet declares). `FONT_PAIRINGS`/template
  manifests/`_google_fonts_stylesheet_url` all repointed to the local
  paths; reinstalled all 6 builtins to refresh their DB rows. Template
  Packages don't need to bundle font files themselves — every deployment
  of this codebase already ships the complete fixed font set as part of
  the repo/Docker image, so a package's `google_fonts_url` always
  resolves locally regardless of which install exports/imports it.
  Verified live: zero network requests to any google/gstatic domain.

**Open / blocked:**
- ~~Table and Video Gallery still need the Image Accordion editing-form
  treatment~~ — done, see the "Table + Video Gallery editing forms" entry
  at the top.
- ~~Image Accordion display-style variants~~ — Carousel and Masonry done,
  see the entry at the top.
- ~~Icon pack integration~~ — **the item was stale, and investigating it
  turned up dead code instead.** It described wiring an imported icon
  pack into the pickers, but that whole design was already replaced: the
  pickers are a curated ~500-emoji grid, and there is no icon-pack import
  path anywhere. What the old design *had* left behind was 46 unreferenced
  Bootstrap SVGs under `static/icons/bootstrap/` and `source`/`style`
  parameters that `render_icon`/`icon_choices_for` accepted and ignored,
  threaded through two route contexts and three templates purely to keep
  a removed feature's shape alive. All removed. If bundled icon sets are
  ever wanted again, that's a fresh feature, not a wiring job.
- ~~Panel descriptions compacted into headers with hover-info "?"~~ —
  done, and Phase C is now finished. A shared `panel_help`/`panel_section`
  macro (`partials/panel_help.html`) puts the explanation behind a "?"
  beside its heading; the text stays real DOM text, so it is selectable
  and reaches a screen reader, and the button is focusable so it works
  without a mouse. Template & Layout went from ten prose blocks to one
  "?" per section. Deliberately NOT converted: the JS-driven status lines
  (`cms-tools-hint`, `cms-selected-style-hint`), the empty/no-theme state
  messages, and the Fonts panel's live "which font is applied to each
  role" readout — those are feedback and data, not descriptions, and
  hiding them behind a hover would be a regression.


## Shade spreads: where those numbers came from (2026-08-26)

Moved out of `services/design.py`, which now carries the two rules that
bound a change and a pointer here. The measurements, over all 72 shipped
colours:

How much COLOUR the eleven shades of each palette colour carry as they
move away from the colour itself. The page paints fills from the light
end and text from the dark end, so this is the one control that decides
how much tonal depth a three-colour site has — the answer to "give me
more than three flat colours" without asking anyone to choose nine.

Named rather than numeric, and site-wide rather than per colour, for
the same reason Corners and Depth are: an admin can picture "Subtle"
and cannot picture "0.62".

The variation is carried almost entirely by `sat_ease` — how fast
colour drains out toward the ends — and barely at all by `spread`, the
distance the scale reaches. That split is not a preference, it is what
the numbers allow: the page sets text from the dark end on fills from
the light end, so compressing the scale compresses that pair's
contrast. Measured over all 72 shipped colours, a spread of 0.80 put
two ramps out of order and dropped the worst pair to 4.7:1, under the
4.5:1 AA needs once rounding is counted; 0.85 was the floor. Saturation
has no such limit — across the whole range every ramp stays in order
and no pair falls below 6.8:1, while the colour left in a light fill
more than doubles. So the control varies what is free to vary.
`curve` is what carries the difference. Saturation alone was almost
invisible on a real page: it only bites at the far ends of the scale,
and the far light end is nearly white, where a doubling of saturation
is a couple of values of chroma nobody can see. `curve` bends how fast
the scale descends from its light end INTO the colour, which is where
the fills a page actually paints with live — steps 100 and 200. Below
1 they dive into colour immediately; above 1 they hug the light end and
stay pale.

It is safe for the same reason the saturation was and the compression
was not: bending the path between two fixed endpoints never moves the
endpoints, so the contrast between the light fill and the dark text is
identical at every setting.

Where each number came from, since none of them is a taste call:

  Subtle's curve stops at 3.0. Past 3.2 the light steps crowd so close
  to the light end that two of them land on the same value once
  rounded to 8 bits, and a scale with a flat spot in it is a broken
  scale. Its dark_curve stays at 1.0 deliberately — bending BOTH
  halves is what put six ramps out of order and dropped the worst pair
  to 3.7:1 at an earlier attempt, because the dark half is the text.

  Bold pulls its light end 38% of the way back toward the colour
  (light_spread 0.62), which is what actually puts colour in a fill,
  and deepens the dark end to buy back the contrast that costs. It
  lands at 7.4:1 — the same neighbourhood as Balanced's 7.3:1.

Measured across all 72 shipped colours, average chroma of the fill at
step 100: 3, 23, 92. Thirty times the colour between the ends of the
control, with every ramp in order and no pair below 7.3:1.


## Corner presets: the full derivation (2026-08-26)

Moved out of `services/design.py`, which keeps the geometry and the three
properties that bound a change. The reasoning in full:

Corner-radius language — bridged into --site-radius, which the generic
card/banner/panel classes in site-base.css read via
var(--site-radius, <theme's own original value>), so picking a preset
here can only ever move a template AWAY from its own default, never
break a template that hasn't opted in (see shape_override being NULL by
default). "Organic" is a full border-radius shorthand rather than a
single length because that's what an asymmetric "worn pebble" shape
actually requires — still just one preset choice from the admin's side.

Four of these curve far enough to reach into their own box. A radius of
999px turns a tall card into a stadium, but its content is still laid
out in the rectangle, so on a phone the button at the foot of a pricing
tier sat outside the curve. The shape is not the problem — it is the
whole character of those presets — the padding is: content has to be
inset far enough to clear the corner it is sitting in.

So those four carry the padding their own shape needs, and
_color_override_css in routes/public.py emits it as a rule over the
boxes whose content reaches their edges. The numbers are geometry, not
taste. A corner is an ellipse of radii (rx, ry) centred that far in
from the corner, and content inset by (px, py) clears it while
((rx-px)/rx)^2 + ((ry-py)/ry)^2 <= 1. Solving that for a card at least
as tall as it is wide — which is what all of these are, a card in a
column — gives the pairs below, with a margin over the minimum, since
the binding corner is a full-width button sitting flush with the bottom
of the padding box and one that only just clears the curve stops
clearing it the moment a theme adds a border.

They are deliberately lopsided. On a tall box the curve is at the top
and the bottom, so that is where the room should come from; paying for
it sideways instead just narrows the text for no gain (it cost a
pricing tier 40px of line length before this was split). The Lens and
the Organics curve more deeply again, and their vertical radius is a
share of the HEIGHT, so they hold to roughly two and a half times
taller than wide and want a squarer box past that.

The absolute caps are for the other extreme: a wide box, where a
percentage of the width is a percentage of the LONG side and would pad
a 1100px box by 264px for a corner only 150px across.

Decorative surfaces — a banner, a picture, a button — are left alone:
nothing inside them can spill.

## Asked for, not yet built (2026-08-27)

Raised while walking a real install. Recorded here rather than started,
because each is a feature with a design question in it, not a fix.

### Commerce, properly exercised -- DONE (2026-08-27)

Done, and it found two bugs that only a real purchase could have found.

All four kinds were created and bought through the site with Stripe in
test mode: payment-only, a session pack, a file download, and a posted
item. The session pack decremented on booking (10 -> 9), the booking
produced a real calendar invite, and cancelling it from the admin gave
the session back (9 -> 10). Orders, entitlements and the diary all agree.

What it turned up:

  * **Nobody could pay at all.** `form-action 'self'` is enforced across a
    form's whole redirect chain, so the 303 handing the buyer to Stripe
    was refused by the browser -- silently, and only in a browser.
    `curl` ignores CSP, which is why every check written against that
    flow had passed. See its own entry above.
  * **The stock count could never count.** The line maintaining it sat
    below an early return that fired for exactly the kind that has stock.

Two notes for anyone repeating it. A CHF checkout offers TWINT, Card and
Klarna with none preselected, so nothing typed reaches a card until Card
is chosen; and on a posted item Google's address suggestions cover the
postcode and city fields until dismissed. Both cost an hour of looking at
a form that appeared complete.

The webhook caveat still stands: this install is a LAN address, so the
thank-you-page path plus reconcile is what was tested, and is the
supported route there.

### The CAPTCHA is arithmetic, and that is not enough

The contact form asks "what is three plus four?". That stops a naive
script and nothing else: any language model answers it instantly, and
they are what sends spam now. Worth replacing.

The design tension is real and should be decided deliberately rather than
by picking a library: this app self-hosts its fonts specifically so that
no visitor's IP reaches a third party, and hCaptcha or Turnstile would
put a script from someone else's CDN on every form -- the exact thing
that was removed. Options worth weighing: a proof-of-work challenge
served from this app, a honeypot plus timing heuristic (no visitor-facing
puzzle at all), or accepting the third party and saying so in the privacy
page. The rate limit already in place (5/hour per IP) is a floor, not an
answer.

### A front-end assistant that only answers about this site

An AI chat for visitors, scoped to the site and its services. The whole
difficulty is the word "only": a model given a site's pages will happily
answer questions about anything, invent a price, or promise a refund
policy that does not exist -- and it does it in the owner's voice, on
their page. What it says about their business is theirs, legally and
practically.

So the design has to start from refusal rather than retrieval: what
sources it may draw on (the site's own pages, and nothing else), what it
must decline, whether an answer it is unsure of becomes a contact form
instead of a guess, and whether the owner sees a transcript. The
assistant that already exists is admin-only and proposes content a human
approves -- a visitor-facing one has no such gate, which is the whole
problem.

### WhatsApp to the owner

Two very different features share the name. A wa.me link is a tool
somebody drops on a page, needs no integration, and would take an
afternoon. The Business API means a Meta app, a verified number, message
templates approved in advance, and a webhook to receive replies -- and
it puts conversations with customers inside a third party this app would
then be responsible for.

The first is worth doing on its own terms. The second should not be
started without deciding whether this product wants to hold customer
conversations at all.

## Driving the editor from outside broke a live site (2026-08-27)

Worth recording in full, because the next person automating this app will
reach for the same shortcut.

**What happened.** To set a Menu's alignment I found its control --
`select[name=menu_align]` -- set its value and dispatched a `change`
event, which is what a click does. The control carries
`onchange="this.form.requestSubmit()"`, so the form submitted. The menu
came back holding one item, and since the header menu is a template zone
shared by every page, every menu on the site was lost at once.

**Why.** The Menu tool's page checkboxes have NO `name`. They are read by
JavaScript, which assembles a single JSON `menu_items` field. That
assembly only happens while the tool's panel is open and its script has
run. Submitting the form without it posts an empty item list, and the
tool faithfully rebuilds the menu as empty. Nothing validated it, because
an empty menu is a legitimate thing to want.

**Three rules that follow.**

1. **A form whose fields are assembled by JavaScript cannot be submitted
   from outside that JavaScript.** Check for unnamed inputs before
   posting anything: if the control that matters has no `name`, the form
   is a view over state held elsewhere.
2. **Re-applying the template does not repair it.** `refresh_site_menus`
   was tried first and did nothing, because the menu's items live in the
   section's own markup (`data-menu-items`), not in the pack.
3. **The repair needs the exact stored shape**, which is
   `{"key": "p<id>", "type": "page", "id": <id>, "icon": "", "parent": null}`.
   Posting `{"id":..., "parent":null}` returns 200 and silently drops
   every item -- the second failure of the same evening, from guessing a
   payload instead of reading one back first.

**What should have been done**: read the existing `data-menu-items` off
the element, modify the one key in question, and post that back -- or
leave a setting that has a control to the person whose site it is, which
is what the defect-or-choice test in CLAUDE.md already says.

## Two gaps found by using the thing (2026-08-27)

### A template cannot ship site-wide furniture

Three built-ins shipped a Breadcrumb on their About page and nowhere
else, which is not a decision anybody would make: a breadcrumb that
appears on one page of six is worse than none, because it reads as a
mistake on that page and its absence reads as a mistake on the others.

It was not a decision. It is the only thing a template CAN do. A pack
carries `pages/`, and every section in them lands in a page's body --
there is no `zone` key, so a template cannot put anything in the header
or footer zone where it would apply everywhere. The menu is site-wide
only because the SEED builds it into the header zone afterwards, not
because the pack asked for one.

Removed from the three templates, since "none" is the half of "all or
none" that a pack can actually express. The feature worth building is the
other half: let a pack carry header/footer-zone sections, so a template
can ship a breadcrumb, a strapline, or a booking bar that applies to the
whole site. Note when doing it that zone sections are shared, so applying
a pack's content must not duplicate them on every load -- the same
merge-by-slug problem the body pages already solve.

### The shop speaks one currency and never says which

A product's price is a number and a currency chosen per product, and a
visitor sees it whoever and wherever they are. Three separate things were
asked for and they are not the same feature:

  1. **A base currency for the site.** The smallest and the most clearly
     missing: one setting, used as the default for every new product, so
     a shop cannot end up with prices in three currencies by accident.
  2. **Regional detection.** Show a visitor their own currency. Needs a
     source for the visitor's region (their IP, which is a privacy
     question this app has been careful about, or Accept-Language, which
     is weaker but local) and a rate source.
  3. **A selector with live conversion.** The visitor chooses. Needs a
     rate feed, a refresh policy, and a decision about what happens at
     checkout -- Stripe charges in ONE currency, so a converted price is
     an estimate unless the Stripe price is created in that currency too.

The trap in 2 and 3 is that a displayed price is a representation and the
charge is the fact. Showing EUR and charging GBP is how a shop gets a
chargeback. Whatever is built, the checkout page must state the currency
the card will actually be charged in.

Worth doing 1 first regardless: it is a setting, it has no dependencies,
and it makes the other two coherent by giving them something to convert
FROM.

## The builtin-fork trap (2026-08-27)

A live install accumulated three templates all called "Life Coaching
(your copy)". Reproduced, because "how did that happen" deserved an
answer rather than a guess:

    activated the builtin      copies=0  active=Life Coaching (builtin)
    edited one text block      copies=1  active=Life Coaching (your copy)
    activated the builtin      copies=1  active=Life Coaching (builtin)
    edited one text block      copies=2
    activated the builtin      copies=2
    edited one text block      copies=3

**Activate a builtin, edit anything, and it forks.** Do that cycle again
and you get another copy. Re-running the setup walk-through does NOT fork
on its own -- it was the edit each time, which is why this was invisible:
nobody thinks of typing a word as creating a template.

The user sequence that produces it is entirely ordinary: try a template,
tweak something, decide to start fresh, activate the original again,
tweak something. Two abandoned copies, no warning. Until 2026-08-27 they
were also identically named, so the library became unreadable -- that
half is fixed (the name is disambiguated like the slug always was).

The forking is right: it stops an edit modifying a shipped template.
What is missing is that nothing notices a copy of that exact builtin
already exists. Three options, none of them obviously correct, which is
why this is written down rather than acted on:

  * **Reuse the existing copy.** Simplest, and wrong if the owner has
    since saved changes into it -- they activated the BUILTIN, so they
    asked for the shipped look, not their old copy of it.
  * **Fork only when the existing copy has diverged** from its builtin.
    Correct, and needs a comparison that is meaningful across theme
    files and content.
  * **Say something.** "You already have a copy of this template" with
    the choice offered. Cheapest, honest, and puts it in front of the one
    person who knows which they meant.

The third is probably right for a product whose whole argument is that a
novice should never be surprised by what it did.

### What to do about the fork -- the two designs, weighed (2026-08-27)

First, a fact that removes one of them: **a forked template already never
forks again.** `fork_active_builtin` returns early unless the active
template `is_builtin`, and three edits to a user-managed copy leave the
count unchanged. The builtin / user-managed distinction exists and is
already load-bearing. So "make forks not fork" is not a change to make;
it is the current behaviour.

That leaves the only route to a second copy: deliberately activating the
BUILTIN again, then editing. Which points at the other design.

**No forking; edit the active template; offer to reload the shipped
version.** The reason this works here, and would not in most products, is
that the pristine data is already immutable and already present: every
builtin lives as `app/data/template-packages/<slug>.zip`, rebuilt from
source at image build time, reinstalled on boot, hash-checked. Nothing an
owner does can damage it. The fork protects a thing that cannot be lost.

What it buys: an entire concept leaves the owner's head. No copies, no
library filling with near-identical entries, no question of which one is
"mine". Editing a template edits the template, which is what everybody
assumes it does anyway. And "Reload the shipped version" is one action
sitting next to Load Content, which already means something adjacent.

What it costs, and both are worth stating before anyone builds it:

  * **"Bakery" on this install may no longer be Bakery.** A template's
    name would no longer promise what it shows. Mitigated by marking a
    modified builtin as changed, which also gives the reload action
    something to be enabled by.
  * **The reload is destructive and must say so** -- it overwrites the
    look and, if content is included, the pages. The confirm dialog and
    the save-first checkbox already exist for exactly this shape of
    action.

Recommendation: this one, and mark a modified builtin so the name never
lies. It is fewer concepts, and the safety it gives up was protecting
something that was never at risk.

### Responsive preview in edit mode (asked for 2026-08-27)

A dropdown in the editing header to switch the view between desktop,
tablet and phone, without leaving the page or resizing the window.

Worth building for a reason this session demonstrated repeatedly: almost
every layout fault found on this site was a phone fault, and each one was
found by measuring at 390px rather than by looking at the desktop view.
An owner editing their own site has no way to see that at all.

Note when building: the editor's own chrome (the dock, the tool panels)
must not be scaled with the page -- it is the app talking, not the site,
and it should stay at its own size while the CANVAS narrows. That is the
chrome-vs-content boundary again, in a new place.

### Forking, settled: ask, name it, and only when a LOOK changes (2026-08-27)

The design to build, refined from the owner's proposal after finding what
the fork actually does.

**What it does now.** `fork_builtin_before_content_edit` is a
before_request hook that fires on any POST to a content endpoint: "the
first content change of a site running a built-in makes it theirs". But a
content edit writes to pages and sections -- the SITE's data. It does not
touch the template package or its row. So the fork on a content edit is
about identity, not protection: it exists so that what you are running is
called yours once you have typed in it.

**Which suggests the boundary is in the wrong place.** The template's own
data is its look: `color_overrides`, `font_overrides`, the shape, the
theme files. Changing THOSE on a builtin genuinely writes to a shipped
template. Changing a paragraph does not.

So:

  * **Content edits do not fork at all.** They never needed to. A site
    running the shipped Bakery with its own words is exactly what it
    says it is.
  * **Changing the LOOK of a builtin asks**: "Make this a custom copy?"
    -- because that is the first moment anything shipped would be
    altered.
  * If no copy of that template exists, it makes one, and the owner names
    it. A name they chose is a name they will recognise in the library.
  * If a copy already exists, it asks: **overwrite that one, or make
    another?** -- which is the case that produced three identical entries
    on a live install, and the one no automatic rule can answer, because
    only the owner knows whether the old copy still matters.
  * The library shows the two kinds apart: as shipped, and custom.
  * A template can be activated as often as you like and nothing is
    created, because activation is not a change.

**The open question before building**, and it should be answered rather
than assumed: `_retire_foreign_pack_pages` deletes pages whose
`source_template` differs from the active slug. If a site keeps running
the builtin instead of a fork, check what that does to pages the owner
has since edited when they later activate something else. The fork may
have been quietly protecting those, in which case the fix is to update
`source_template` when a page is edited, not to keep the fork.

The result an owner sees: nothing appears in their library that they did
not ask for and name. Which is the whole argument of the product, applied
to the one place it was not.

### Templates have a lifecycle: source, custom, promoted (2026-08-27)

The owner's final shape, and it resolves the fork by making it a stage
rather than an accident.

**Two kinds, one rule.**

  * A **source** template never changes. The sixteen shipped ones are
    sources; so is any custom template the owner has finished with and
    promoted. A source is a starting point, and a starting point that
    moves is not one.
  * A **custom** template is work in progress: forked from a source,
    freely editable, and the only kind that can be written to.

**The fork becomes a question, asked at the only moment it matters.**
Change the LOOK of a source -- its colours, fonts, shape, theme -- and it
asks: you have changed a source template, do you want to fork it? If yes
and no copy exists, it makes one and the owner names it. If a copy
already exists, it asks whether to overwrite that one or make another,
because only the owner knows whether the old one still matters. Content
edits do not fork at all: they write to the site, not the template.
Activation never creates anything, however often it is done.

**Promotion closes the loop.** When a custom template is finished, the
owner moves it to the sources. It becomes immutable like the rest, and
from then on editing it asks the same question and forks the same way.
That is what makes the model hold together rather than being a special
case for shipped things: "shipped" stops being a category the code cares
about, and `is_builtin` becomes one reason among two for a template being
a source.

**What this replaces**, in the code: the fork guard currently reads
`if not active["is_builtin"]: return None`. It would read "is this a
source", which is true for shipped templates AND promoted ones, so a
promoted template gets the same protection without a second mechanism.

Three things to settle while building:

  * A promoted template lives in `static/themes/<slug>/`, not in the
    shipped zips, so the boot-time reinstall must leave it alone. It
    already does -- reinstall is driven by the zip list -- but a
    promoted template needs its own flag rather than borrowing
    `is_builtin`, or a rebuild would try to find a package for it.
  * Promotion should be reversible while nothing depends on it, and
    refused once something does -- the same shape as "the active
    template cannot be deleted", which is the guard that made today's
    cleanup safe.
  * The library shows the two groups apart, so an owner can see at a
    glance what is a starting point and what is theirs in progress.

### Packaging happens at promotion, not before (2026-08-27)

A custom template is not packaged and cannot be exported. Promoting it to
a source is what packages it, and only then is it distributable.

This is the piece the model was missing, because packaging currently has
no moment. `export_package_zip()` is offered on any library entry at any
time, so a half-finished custom template -- one an owner is still moving
things around in -- can be handed to somebody else as though it were a
thing. It isn't. It is a draft.

Tying the two together gives each a job:

  * **Custom**: live, editable, private to this install. No zip, no
    export, no inventory. Nothing to keep in step with the edits,
    because there is no artefact yet.
  * **Promotion**: the moment the artefact is built. Write the zip,
    compute the `install.json` inventory -- every page and its section
    count, every picture with size and checksum -- and freeze it.
  * **Source**: immutable, packaged, exportable, distributable.

**Promotion is also the right place for the completeness check**, and
this is the strongest argument for the whole arrangement. A package once
went out silently missing its pages and pictures, which is why the seed
now installs all sixteen builtins through the same import path on every
boot. Promotion is a deliberate act with a person waiting on it -- the one
moment where "this template references four pictures and three of them
exist" can be reported and refused, rather than discovered by whoever
installs it later.

**Note for whoever builds it**: this supersedes CLAUDE.md's "Exporting to
a .zip stays a separate, always-available action on any library entry,
builtin or not" (in the Template Packages section). Export stops being
always-available and becomes a property of being a source. Update that
line in the same change, or the two documents will disagree about
something a reader has no way to test.

### Nobody could pay, and every command-line check said they could (2026-08-27)

The shop rendered, the basket totalled, `/checkout` answered `303` to a
`cs_test_` Stripe session. In a browser the Checkout button did nothing at
all.

`form-action 'self'` is enforced across a form submission's **whole
redirect chain**, not just its immediate target. Checkout is a form that
posts to this site and is then redirected to Stripe's payment page, so the
browser refused the redirect and silently stayed on the basket. One line
in the console; no error on the page; nothing in the server log, because
from the server's side the request was served perfectly.

`curl` ignores CSP entirely, which is why every check written against this
flow passed. The whole of commerce -- the Buy Button and the basket both,
since they share the one route -- had never worked in a browser, and could
not have been found without one.

Fixed by naming the payment host: `form-action 'self'
https://checkout.stripe.com https://pay.stripe.com`. Proved by serving the
same form and the same 303 under the old header and the new one and asking
a real browser where it ended up: blocked, then reached.

**Two checks in `tools/prod_check.py`** so it cannot come back -- that the
directive admits Stripe, and that it has not been widened to `*` or a bare
`https:` while doing so.

The general lesson is about the shape of the test, not about CSP. A check
that speaks HTTP tests the server; a browser is a second implementation
with rules of its own, and anything whose failure mode lives in those
rules -- CSP, mixed content, cookie policy, autoplay, clipboard -- is
invisible to every tool that is not one.

### A curve needs an inset, and the inset depends on the box's shape (2026-08-27)

Shop items on a pill-cornered site drew an ellipse and then wrote the
name, price and button into the rectangle's corners, outside it. The
shape was the owner's (Corners is a control, so the roundness is a
choice); the spill was not (nobody chose a button hanging off the edge).
So: a defect, by the two questions in CLAUDE.md.

The mechanism was already solved and simply not wired up. Strongly-curved
shapes declare `--site-radius-pad` so content clears the curve, and seven
surfaces read it. The commerce and card surfaces took `--site-radius` for
their corners and kept a flat `padding: 16px`. Measured against the
ellipse equation, every corner of every child: worst point **1.43** before
(1.0 is the edge), **0.71** after.

**The new part.** Applying the same inset to `.cms-file-card` turned a
420x80 row into 420x352. `--site-radius-pad`'s components are
percentages, and a percentage padding resolves against the containing
block's WIDTH -- on any side. On a block that is roughly as tall as it is
wide that is fine. On a short wide row it means the TOP inset is sized
from the width, and 24% of 420 is 100px of padding above an 80px box.

Underneath the arithmetic is a geometric fact: a curve cuts a box where
the box is longest. A tall block is cut at its corners and needs both
insets; a short wide row is cut at its ENDS and needs only an inline one.
One variable cannot answer both, so the three short-wide surfaces
(`.cms-file-card`, `.cms-subscribe-note`, a collapsed
`.cms-faq-style-cards .cms-faq-item`) were left alone rather than given a
fix that is worse than the fault -- a companion inline-only variable,
declared by each shape preset beside the one that exists, is the shape of
the answer when it is worth building.

Note also that `[data-corner-style]` was EMPTY on this site: the template
simply is curved, setting `--site-radius` in its own CSS. Anything keyed
off that attribute would have matched nothing here, which CLAUDE.md
already warns about and which is why the fix reads the variable instead.

### A container is not an object, and 999px is not "very round" (2026-08-27)

The shop still read as odd after its content was brought inside the
shape, and the owner named it: overuse of the pill. Measured, one page
carried the same 999px at four nesting levels -- section, panel, card,
button -- including a **952x940 section drawn as one enormous ellipse**
around unrelated content.

The statable fact: `border-radius: 999px` does not mean "very round
corners", it means "as round as this box allows". On a 130x50 button that
is a pill and it is the idiom. On a 952x940 section the box stops having
corners at all and becomes an ellipse -- a different shape, which the
control that produced it does not name. The control is called Corners.

So the line is **container versus object**. A card, a button, a picture
is an object and wears its own shape; a section or a panel is a region
holding objects that already have shapes, and when its curve degenerates
it draws a huge oval around things with no relation to it. Containers are
now capped (`clamp(0px, var(--site-radius, 0), 56px)`), objects untouched.

This is the same judgement the video cap already makes in this file --
there, a 999px radius clipped the play bar off and the player could not be
used. Same cause, different symptom.

Known limit, shared with that cap: `clamp()` takes lengths, so a `50% /
30%` lens or an organic blob radius makes the declaration invalid and it
is dropped, leaving those shapes uncapped. Worth a proper fix when a
lens-cornered site is looked at.

One further thing seen and NOT changed: a shop card pushes its button to
the bottom (`margin-top: auto`) so buttons line up across a row, which
puts content at the top and bottom of an ellipse -- exactly where the
shape is narrowest -- and leaves the middle, the widest part, empty. The
alignment is deliberate and correct on a rectangular theme, and there is
no way to select on "the radius is extreme", so it stays until the
container/object distinction above is available as something CSS can ask
about.

### One buyer, one link (2026-08-27)

Three purchases produced three different `/my/<token>` links, and the
owner named the consequence: a link that changes every time is not a link
anybody can keep.

It was not an oversight, it was a consequence. Only the token's HASH was
stored -- deliberately, so a copy of the database could not open anyone's
page -- and a hash cannot be turned back into a link. So anything that had
to SHOW a link had no choice but to mint a new one, and every purchase
issued another. All of them worked, which is why it looked like a
cosmetic oddity rather than the feature failing at its one job.

The token is now also held encrypted (`crypto`, the key the API keys
already use), so the buyer's live link can be shown again. Stated
plainly, because it is a real change of threat model: a copy of the
database alone used to be useless, and now a copy of the database
TOGETHER with the encryption key would open a buyer's page. That is the
bar this app already sets for the Stripe secret key sitting in the same
file, and `services/backup.py` leaves the key out of an archive by
default for exactly this reason.

The page also stopped saying "there's no password". True, and not
something to advertise -- it tells anyone reading over a shoulder what
the link is worth.

**Still open, and the owner asked**: whether to protect a purchase
further. The cheap and meaningful option is to ask for the buyer's email
address before the page opens -- something you have plus something you
know, no account, no password to forget. Not built: it puts friction on
somebody who has just paid, and that is the owner's call.

### An internal marker reached a person

The Bookings screen read: `Couldn't read your diary from Cal.com --
[could-not-reach] TimeoutError: The read operation timed out`.

`[could-not-reach]` is a sentinel this codebase adds so a caller can tell
"the provider said no" from "nothing answered" -- two problems with
different fixes. It was only ever translated in one place, the Test
Connection button, and every other surface printed the raw string. Eight
of them.

Now one function, `integrations.explain(error, name)`, sits between any
provider error and any person: it rewrites the unreachable case into a
sentence that says whose fault it is ("a network problem on the machine
running this site, not a problem with your key") and returns everything
else untouched, since most callers already have their own sentence to put
it in. A marker that must never be read by anybody should have exactly
one exit.

### The stock count could never count (2026-08-27)

Selling the physical item left "Only 3 left" saying 3, and the order read
"Nothing to unlock -- this was payment only".

```python
if not rule or rule["kind"] not in (KIND_DOWNLOAD, KIND_CREDIT):
    return None                     # physical leaves here
...
if rule["stock"] is not None:       # never reached for physical
```

Stock is only ever set on a physical item, and the one line maintaining
it sat below an early return that fired for exactly that kind. The
docstring even said physical returns None -- the author knew, and put the
stock update underneath anyway. So the count was decoration: it displayed,
it could be edited, and it never moved.

Fixed by counting first, before any branch, for every kind that has a
count. A posted item is now also recorded as an entitlement, which is what
it is -- something a sale owes somebody -- so the owner's Orders screen
says **To post: 1 item** instead of "payment only", which actively hid the
one thing that needed doing. The buyer's page ignores the kind, because
there is nothing for them to claim.

### A time with no timezone is a missed appointment

The buyer was told **09:00 (Europe/Zurich)**. The owner's Bookings screen
said **07:00**, unlabelled. Same booking.

Underneath was a worse trap: `describe_slot` did not convert, it
*labelled*. It formatted whatever offset the string carried and appended
the zone name, so asking for a Zurich time handed back a UTC one wearing
a Zurich label. The buyer's page was right only because the string it
stored already carried the local offset -- correct by luck.

It now converts, and a time that really is UTC says "UTC" rather than
looking local. An unknown zone name, or an image with no tz database,
falls back to showing the time as it came rather than claiming a
conversion that did not happen.

### Commerce becomes one screen with tabs, and Orders can be asked a question

Products, Orders and Bookings were three dashboard buttons for one
subject. They are now one **Commerce** button with tabs, the shape Email
already had. The tab list lives in ONE partial rather than being pasted
into each template -- which is how the Email section's three copies can
already drift when a fourth screen is added.

Orders gained filters by buyer, product and date, and -- found while
building them -- **it never said what was bought**, only an amount and a
Stripe reference, which answers neither of the two questions the screen
exists for. Filters are plain GET controls, so a filtered view is an
address that can be bookmarked and sent to somebody, and the choices
offered are only the ones actually present, so a filter can never select
nothing.

Two smaller things fixed in passing. The cancel dialog offered **"Cancel
booking"** next to **"Cancel"** -- one undoes the booking, the other
undoes the click; the confirm now says "Yes, cancel it". And a Jinja trap
worth knowing: a dict key called `items` is unreachable, because
`entry.items` resolves to `dict.items`, the method, and the template gets
something it cannot loop over.

### A lock the buyer chooses, on a link that stays the same (2026-08-27)

Two things were asked at once: one URL per buyer rather than one per
order, and a way to protect it.

The first was already fixed and is now proven on the live site -- two
purchases by the same person returned the identical link. What arrived as
three links was from before that deploy.

For the second, the choice was between a password on the existing link
and a sign-in page where a buyer types their email. **The link won**, and
the reason is worth writing down: an email typed into a public form is a
credential, and it drags in everything a credential needs -- rate
limiting, address enumeration, a reset flow, and an account for somebody
who only wanted the thing they bought. The link is already the credential
and it is already delivered. So the password is a SECOND thing, opt-in,
offered once, on a page they reached by proving they had the link.

**Hashed, not encrypted, and that distinction is the whole point.** The
token above is encrypted because it has to be SHOWN again. A password
never does -- it is only ever compared -- so nothing should be able to
read it back. Same database, two secrets, two different storages, chosen
by what has to be done with each.

Three details that follow from it not being an account:

  * **The owner is the reset mechanism.** There is nowhere safe to send a
    reset that is not the address the link already went to, so a forgotten
    password is a message to the owner, who clears it from the Orders
    screen. That was the conversation anyway.
  * **Unlock attempts get their own budget.** They shared the
    `login_attempts` table with the admin login, so a stranger guessing at
    a buyer's orders page could have locked the OWNER out of their own
    admin. The table now records which kind an attempt was.
  * **The answer lives in the session, never in the URL.** A password in a
    link is worse than no password.

### Nobody told the seller, and nobody sent an invoice

Asked, checked, and both were true. One email went out per sale, to the
buyer. The owner learned about a sale by opening the Orders screen and
noticing a new row -- fine for a download, which delivers itself, useless
for something in a cupboard waiting to be posted.

There is now a second message, to the site's own contact address, that
opens with what to DO ("ACTION: post 1 item") and then says who, what and
how much. It carries no link, because it is a job list rather than a way
in. It is sent inside its own try, after the buyer's: a mail failure to
the owner must not cost the buyer the email they actually need.

**A receipt is not an invoice**, and the checkout was asking for neither.
Stripe emails a receipt only if the account has that switched on, and a
receipt is not a numbered document anybody can put through their books.
The session now sets `invoice_creation[enabled]`, so Stripe produces and
sends a real invoice carrying the seller's own business details -- which
is right, because this app has no business generating tax documents.

### A download that outlives its hosting

The email said a download was waiting and the page said "a few
downloads", where there was one. Neither said for how long, and the
answer was "forever, but the link dies in thirty days" -- the worst
arrangement available: the file never expires, and the way to it quietly
does, while the email tells them to keep it.

Both halves fixed, in opposite directions. **The link now rolls forward**
-- using it pushes its expiry out again, so a link in use never dies and
an abandoned one still ages out. And **downloads now expire**, because
nobody hosts a file forever and pretending otherwise is a promise made on
the owner's behalf. Thirty days by default, settable beside the session
term (they are different promises: one is time the owner will honour, the
other is time they keep paying to host). The buyer is told the DATE, not
a duration -- "30 days" needs them to remember when they bought it, and
they are reading the email weeks later.

### The field types nobody listed (2026-08-27)

The Orders filter row looked broken: two selects at one height beside two
date boxes at another, in a thinner border and a smaller face, wrapping so
that one field sat alone on a line.

The layout was only half of it. The shared control rule named
`input[type=text]`, `password` and `file` -- so `date`, `email`, `number`,
`tel`, `url` and `search` inputs kept the BROWSER's defaults, everywhere
in the admin. Not a filter-row problem at all: the setup wizard's email
fields and Legal's number fields had it too, and had had it all along,
because nothing had ever put one of them next to a select where the
mismatch was visible.

An attribute-value selector that has to be extended for every value is a
list that will be wrong again. It is now complete for the types this admin
actually uses, and the row itself is a grid rather than a wrapping flex
line, so controls share a column width and wrap as whole units.

**Orders also filters by what an order DELIVERS** -- sessions, a
download, something to post, or payment only. That is a different
question from what it was called: "everything still waiting to be posted"
is a working list, and the product name cannot answer it. Payment-only is
the absence of any rule, so it is a kind on the screen while being a row
nowhere.

And the sale notice to the owner **is sent even when the owner is the
buyer**. It was suppressed when the two addresses matched, which is tidy
in production and hides the feature from every owner testing their own
shop -- which is everybody, on their first day. The two messages say
different things: one is a way back to what was bought, the other is a
job list.

### Capping a container was overriding a choice (2026-08-27)

The container cap from earlier today is **reverted**. It was the same
mistake this file already records about centring a menu: a shape somebody
picked from a control is a choice, and flattening it in CSS overrules a
person. Corners is a control. The pill on a section is the look.

What was actually wrong was never the shape -- it was content sitting
OUTSIDE it, and that is fixed where it belongs, by insetting the content.
The two caps that remain are the video and the textarea, and both are
there because the shape makes the thing unusable rather than unfamiliar:
a play bar clipped off the bottom edge is not a look.

Worth keeping the failure shape in mind: "this looks like too much" is a
report about taste, and the fix for taste is a control, not a rule that
takes the taste away from everybody.

Note also what the investigation turned up, which was not the cap at all:
`--site-radius` had become unset on the live site because the site's
Corners setting had moved to Auto, and no template's `theme.css` sets it
-- the built-ins state per-kind defaults (`--corner-card`, `--corner-hero`
and so on) and leave the site-wide variable to the owner. So a template
cannot carry a pill: the shape is the SITE's setting, not the template's,
and activating one does not restore it. That is a real gap in "a template
brings a look" and belongs on the list beside the header/footer-zone one.

### A basket is the smallest box on the page

The basket badge hung outside its own curve. Measured: a 69px-wide block
handed 22% of its own width as side padding, leaving 39px of room for a
67px link. Percentage padding shrinks with the box; the link inside it
does not.

The rule that gives a short strip its side clearance already existed and
already listed the menu and the breadcrumb. The basket -- the smallest and
worst affected of the three -- was not on it. Same class of thing, same
rule, one more selector.

**Three more basket styles** while there: just the bag with no number (a
header that would rather not put a running total in front of somebody
still reading), a solid button, and the word with a count and no picture.
The style class now travels onto the rendered anchor, the way the
alignment class already had to, because the marker div holding it is never
what a visitor sees.

**And the Menu gained the pill badge** the Breadcrumb already offered --
filled and outline. Its own entry rather than a corner setting, because a
menu can be pill-shaped on a square-cornered site and often should be: it
is the one row where the shape does the work of separating one word from
the next.

### A basket on a row of its own (2026-08-27)

The header zone stacks its sections in a column -- one section, one row --
so a basket in its own section always landed UNDER the menu with the full
width of the page between them. `margin-left: auto` pushed it right, which
made it a lone box in the corner of an empty second row rather than a
basket in the header. The zone was 222px tall to hold it.

Nobody chose that and no control offers otherwise: the basket's alignment
control says left, centre or right within a row, and says nothing about
which row. So the fix is the app's to make.

A basket set to the RIGHT is now lifted out of the flow into the same
top-right corner the burger toggle already uses -- the menu keeps the full
width it was centred in, and the zone came back to 130px. Left and centre
stay exactly as they were, because those are positions somebody picked and
moving them would overrule a choice.

Two exceptions, both for the same reason -- there has to BE a spare
corner: not below 768px, where the stacked row is right and the corner is
not free, and not in the minimal layout, whose own toggle already lives
there.

### A rule that looks for a tool has to look for what renders (2026-08-27)

The basket panel kept its wrong size through two attempted fixes, and
neither was a padding problem in the end.

`.block-html:has(.cms-basket)` matches nothing on a page a visitor sees.
The `.cms-basket` div is a MARKER -- `render_basket` replaces it outright
with an `<a class="cms-basket-link">` -- so the class the rule looks for
exists only in stored markup. `render_basket`'s own comment says this
about the alignment class, and the lesson generalises to every rule that
has to find a basket: **select on what renders, not on what is stored.**

It is a quiet failure, which is what makes it worth the entry: a
`:has()` that matches nothing does not error, it simply does nothing, and
the symptom is that a fix "did not work".

The sizing either side of it was wrong in both directions. Percentage
padding gave a 69px block 22% of its own width and left 39px of room for
a 67px link, so the count hung outside the curve. Borrowing the menu's
32px was the opposite: a 131x92 panel around a bag and a number. Its own
figures now -- `8px 14px` and `width: fit-content` -- and the panel is
96x51, with the worst corner against the curve down from **1.31 to
0.39**.

**Five basket pictures** rather than one hardcoded bag: bag, basket,
trolley, parcel, price tag. A bakery, a bookshop and a hardware supplier
reach for different shapes, and the icon is the one part a shopper reads
before any word.

**And the pill menu moved up a level.** It was added as a button STYLE,
which put it one dropdown below where anybody looks -- the Breadcrumb
offers "Pill badge" in its own Style list, and two tools naming the same
look at different depths is how an editor stops being learnable. It is
now a top-level menu style. Everything that asked "is this buttons?" now
asks "does this draw buttons?", because a pill menu is a button menu and
only its shape differs.

### Centring a last row that is not full (2026-08-27)

Four products in three columns left the fourth hard against the left
edge, which reads as a mistake anywhere and, inside a strongly curved
section, puts it where the shape is narrowest. Asked for: one product on
the centre line, two straddling it, three filling the row as before.

**Twice as many columns as products across, each product spanning two.**
That is the whole trick -- a half-column step exists, so a short row can
be centred on it. `:nth-child(3n+1)` means "first in its row", so a
`:last-child` that is also first in its row is a row of one.

Two things went wrong on the way, and both are worth keeping.

**Flex was the obvious answer and it was wrong.** `justify-content:
center` centres a short last row for free, and it silently tripled the
cards' padding: percentage padding resolves against the CONTAINING BLOCK,
which for a grid item is its own grid area (234px) and for a flex item is
the whole flex container (742px). `--site-radius-pad` is percentages, so
a card went from 131px of content to **26px**, with the button spilling
out of it. Anything that changes how these items are laid out has to keep
the containing block the size of one card.

**Two overlapping media queries argued, and the earlier one won.** Below
600px the grid is a single column, and every placement above had to be let
go -- but the two-column rule from the `max-width: 900px` block also
applied on a phone, and `:last-child:nth-child(2n+1)` (0,4,0) outranks a
plain `:last-child` (0,3,0). Specificity beats source order, so a lone
last product was placed into a column the one-column grid does not have,
and only ODD counts were wrong. Fixed by making the ranges not overlap.
A `max-width` stacked under another `max-width` is not a cascade, it is
two rules that are both live and will be sorted by specificity.

Checked at 8 product counts across 5 widths: 40 combinations, every row
centred, no overflow.

### An email is not a page (2026-08-27)

Measured, because the Newsletters screen makes a claim: *"A newsletter is
just a page. Write it in the normal editor with the same tools you use
everywhere else."* Of that tool menu, in an inbox:

  * **Blog, Shop, Buy button, Contact form, FAQ Reader arrive EMPTY.**
    Each is a marker resolved against live data at render time, and none
    of that data exists in an email.
  * **Search** arrives as a magnifying glass, a **Video gallery** as
    three play triangles, an **Accordion** as labels with no pictures.
  * **Columns** arrives as the literal text `{}` -- its stored JSON.

So the owner is right and the screen is wrong: an email is a different
medium, not a kind of page. `services/email_layouts.py` declares layouts
with named slots, rendered from table-structured templates with every
style inline, because tables and inline styles are what clients actually
render. The wrapper keeps what it owns and what must not become editable
-- the ground, the light card, the sender line, the unsubscribe link.

Note this does NOT break "features are tools, never page types". That
rule is about capabilities on a page. A newsletter composed of email
layouts is not a page with a special type; it is a different thing
entirely, which is why the tools stop being a question.

**A long-standing bug found on the way.** The style inliner PREPENDED a
second `style` attribute, and a browser reads the first -- so a layout
setting white text on a coloured button had the look's link colour put in
front of it, and the label went the same colour as the button under it.
Invisible, and only in some clients. It merges now: the look first, the
element's own declarations last, which is the order that lets the
specific one win inside one attribute. Skipping styled elements instead
was tried and was worse -- it stopped the look reaching anything a
section had styled, which is most of a section.

### A character you cannot see, in a test that cannot fail

Writing that fix, an escaping slip put a literal **backspace (chr 8)**
where a regex word boundary belonged: `<a\b...` became `<a␈...`, which
matches nothing. The loop ran fifteen times and did nothing. The
character is invisible in an editor, in `grep`, and in
`inspect.getsource` -- an hour went into re-reading code that was, as
printed, correct. `cat -A` found it.

Then the sweep found the same character in the CHECKER, in a rule written
as `not re.search(...)`. A pattern that matches nothing makes that rule
pass every time: **a check that cannot fail is worse than no check**,
because it is counted. That rule now proves it can fail before asserting
that it does not.

Two things came out of it. Every backslash escape written through this
pipeline today came out as the character it names, so generated code uses
`chr(9)` and friends rather than escapes. And `email_layout_check.py`
sweeps all of `app/` for control characters, by code, every run.

### The duplicate pictures were not duplicates (2026-08-27)

Reported: the image picker is full of duplicates. Checked by BYTES rather
than by name, because that distinction has caught this project out
before. Of 154 files in the picker, **150 are distinct images** -- four
genuine copies, 2.6MB. So the library was not full of duplicates.

What the eye was seeing is real all the same: **every one of the 77
pictures exists twice, once as `.png` and once as `.webp`**, and the
picker lists files rather than pictures. 154 tiles, 77 pictures, each
shown twice and identical.

The authored templates ship **only** `.webp` -- there is not one `.png`
among them. Nothing on the site references a `.png`; not a page, not the
active theme's own CSS. So all 77 are orphans of a template version that
predated the format change.

**Extracting a package adds files and never removes any.** That is the
whole cause. A reinstall unpacks the new archive over the old folder, so
anything the previous version had and this one does not simply stays --
forever, on every install that ever ran the earlier version, invisible
until somebody opens a picker and sees everything twice.

`_drop_stale_media` now makes the installed folder match the archive.
Reading a zip's index costs nothing next to extracting it, so it runs
even on the boots that SKIP reinstalling -- which is the point, because
an install already carrying the leftovers has a matching stamp and would
otherwise never clean itself. Scoped to `media/` and to files, so a stamp
survives; a missing or unreadable archive removes nothing at all, since
"I cannot read what this should contain" must never mean "so delete it".

The lesson is the one the owner asked about the first time this came up:
**compare the images, not the names.** Doing so this time turned "a lot
of duplicates" into two separate facts -- four real copies, and a picker
counting formats as pictures -- with different causes and different
fixes.

### The duplicate templates had a trigger, and it was protecting nothing

Three entries called "Life Coaching (your copy)", "(your copy 2)",
"(your copy 3)" -- reported three times, and each one carrying its own
duplicate of the template's pictures.

The trigger was a `before_request` that forked the active builtin on the
first content edit: *"the first content change of a site makes it
theirs."* Editing a page writes to `pages` and `sections`. It does not
write to the template package or its row. So there was never anything
about a content edit that needed a copy of a template -- what it produced
was a new template per site, silently, and another one each time the
site happened to be running a builtin again.

The one plausible defence was `_retire_foreign_pack_pages`, which deletes
pages belonging to a DIFFERENT pack when a template is activated -- so
perhaps the fork was keeping edited pages safe by making the active slug
match. It was not. That function spares any page whose `source_template`
is NULL, and `fork_active_builtin` never touched `source_template` at
all -- zero references. The pages kept pointing at the builtin either
way.

Removed. Forking stays as something the owner ASKS for when they change a
LOOK, which is the design already written up above; `fork_active_builtin`
is kept for it. Proved by making three content edits in a row against a
fresh install and watching the template count stay at sixteen.

**A note on the shape of the mistake**, because it is the second one
today: a piece of machinery that fires on every edit, does something
invisible, and is justified by a sentence that sounds like care --
"makes it theirs". Nobody asked for it and nobody could see it happen.
The Basket panel's padding and this both come down to the same question,
which is worth asking of anything automatic: *what did the person do that
asked for this?*

### A badge marks one thing, or it is not a badge (2026-08-27)

The Menu's "pill badge" was added as a BUTTON style: a filled pill on
every item. Put beside the Buttons style, the two screenshots are the
same control with a different corner radius, which is what the owner
said -- rebranded buttons.

The word was already in use in this app and already meant something
precise. The Breadcrumb's pill tints ONLY its current crumb, in
`--accent-100`, with no other marking. A badge marks one thing: where you
are. A filled pill on every item marks nothing.

So the Menu's pill is no longer a button style at all. It carries no
button class, its links stay plain links, and the current page wears the
Breadcrumb's exact declarations -- same tint, same padding, same radius,
and the colour comes from the palette rather than from the button colour,
which is what stops it reading as something to click.

**One fact gets one mark.** The usual current-page treatment is bold plus
an underline; with a badge on top that is three marks for one fact, and
the Breadcrumb's badge carries neither. The badge style drops both.

`tools/design_conventions_check.py` asserts it: the two rules must
declare the same thing, the badge must take a palette colour rather than
the button colour, a badge menu must carry no button class, and "pill"
must not also be offered as a button style. Nothing in a stylesheet stops
two tools drifting apart again, so the rule is checked rather than
trusted -- an editor stops being learnable the moment one word means two
things in it.

### Writing a post should not require knowing what a <p> is (2026-08-27)

The blog editor's Content field was a plain `<textarea>` holding raw
HTML, so somebody writing a post saw
`<p>I used to give burned-out clients...</p>` and had to maintain the
tags themselves.

This is the rule this project already applied once and then left a hole
in: `admin/page_edit.html` had exactly this removed -- "never a raw HTML
textarea as the way to accomplish ordinary styling or layout" -- and the
blog editor kept one.

`static/js/admin/rich-text.js` upgrades any `textarea[data-richtext]`
into a small WYSIWYG. The textarea STAYS in the form, keeps its name and
keeps being what the server reads; it is only hidden and kept in step. So
the route, the model and `blog.post_html()` see exactly what they always
saw, and nothing downstream had to change.

Three details worth keeping:

  * **The command set is the live editor's, minus the page-layout ones.**
    Bold, italic, headings, lists, a link. Alignment, fonts and colours
    belong to a section on a page, not to the words of a post -- offering
    them here would be inventing a second, quieter way to style a page.
  * **Toolbar buttons act on `mousedown`, not `click`.** Clicking blurs
    the editable and the selection goes with it, so the command lands on
    nothing.
  * **Old posts still open.** Posts written before the editor existed are
    plain text with blank lines between paragraphs, and `post_html()`
    still renders them that way; the upgrade does the same conversion, so
    an old post shows paragraphs rather than one run-on block.

The icon inserter had to be told about it: it writes at
`selectionStart`, which a hidden textarea no longer has a visible caret
for, so it now inserts into the surface the person is actually looking at.

`design_conventions_check.py` asserts no admin form takes a post's
writing as raw HTML, so the hole cannot reopen quietly in a third place.

### One toolbar, two places (2026-08-27)

The blog editor's WYSIWYG was written fresh, with a smaller command set,
while the live page already had a full one. The owner asked the obvious
question -- why not reuse the live text tool, it has more features and is
prebuilt -- and they were right; this project's own rule says so:
"Before adding a new inline block to a template, check whether the same
interaction already exists elsewhere."

Reusing it whole was not the answer either. `inline-editor.js` is 2,463
lines that bind drag-and-drop, section menus and autosave; loading that
into an admin form to obtain a toolbar is the wrong granularity. The
right seam is narrower and it was already there:

  * **The markup** moved to `partials/wysiwyg_toolbar.html`, included by
    both. `include_media` is the only difference between the callers --
    the live page can upload an image into the words and insert an icon
    from its own grid, an admin form has no upload target and carries its
    own icon control.
  * **The dispatch** moved to `static/js/wysiwyg-commands.js`. Three
    things differ between callers and are passed in, because each is a
    genuinely different question: which editable a control acts on (the
    live page walks up to a section; a form has exactly one), what to do
    afterwards (autosave, or copy into the hidden field the server
    reads), and how to ask for a URL (the live page's modal, or the
    browser's prompt).

The blog editor now has alignment, fonts and colours it did not have, and
sixty-seven lines came out of `inline-editor.js`. Both were exercised in
a browser afterwards -- bold and italic on the live page, bold and the
hidden-field sync on the form, no console errors on either.

**What I got wrong** is worth naming, since it is the same shape as the
automatic fork earlier the same day: I answered "this field needs a rich
text editor" by building one, rather than asking what already answered
it. The smaller build looked like less work and was more code.

### Add to basket, and stay where you are (2026-08-27)

Adding something took the shopper straight to the basket. The code even
said why -- "the way a market stall works: you see what you are holding"
-- and on a page of four products it means being carried away from the
shop after each one and having to find the way back. That is where a
second purchase stops happening.

Now it adds and leaves them there. The basket is a link in the header
with a count on it; that count changing IS the confirmation, and the
basket is one click away whenever they want it.

Built as an upgrade, not a replacement: the form posts and the server
answers either way. With a script the page does not navigate at all --
the count updates, the button says "Added" for a moment and goes back to
itself. Without one, the same form posts and the server sends them back
to the page they were on, and the header count is still honest feedback.

Found while doing it: **a public page renders no flashes at all**, so the
existing `flash("Sorry — that's just sold out.")` had never been seen by
anybody. The refusal travels in the answer now and lands on the button
that was pressed, which is where the shopper is looking.

## Five faults found by using it on a phone and a desktop (2026-08-27)

All five reported from the running site. Three turned out to share one
shape: a rule that was right about the outside world and had never been
asked what it did to this site's own machinery.

### The preview showed nothing, at every width

Two separate headers, both correct-looking, both wrong here.

`frame-ancestors 'none'` and `X-Frame-Options: DENY` say "nobody may put
this page in a frame". The responsive preview in the editor puts this
page in a frame. A page that refuses every framer refuses ITSELF, so the
preview was an empty document at 390, 768 and 1400 alike -- and nothing
reported it, because a blocked frame is a console line in a browser, not
an error the server ever sees. `'self'` and `SAMEORIGIN` still refuse
every other origin, which is the clickjacking protection the rule exists
for; nothing is given away by letting the site frame itself.

Fixing that alone was not enough, and the second half is the more
interesting one. `frame-src https:` says what this page may EMBED, and it
is that wide because a Cal.com booking or a Stripe button has to work.
Over https the site's own origin happens to match `https:`, so the
preview worked once framing was allowed. Over plain http it matches
nothing -- so the preview would have stayed broken on every install that
has not put a certificate on yet, in a way that looked like a different
bug. Naming `'self'` says what is actually meant rather than depending on
the scheme to say it by accident.

**The rule this leaves:** a security directive written about third
parties has to be re-read as a statement about the site's own features.
Three checks in `tools/prod_check.py` now hold both halves.

### The floating basket was there while editing and gone for visitors

The floating basket is `position: fixed`, and the section it came from
has nothing left to hold -- so I hid that section with `display: none`.
A fixed child of a `display: none` parent is not rendered either. It
survived in edit mode only because a later rule put the section back to
`display: block` so the tool stayed clickable, which is exactly the
condition that hid the bug from me: it worked everywhere I was looking.

`display: contents` is the right tool and the distinction is worth
keeping: `none` removes the box AND everything in it; `contents` removes
only the box. When the whole point is that a child escapes its parent,
`none` is never what is meant.

### The dock tabs sat wherever the stylesheet put them

Five fixed offsets down the right-hand edge, often over the thing being
edited, with nothing an admin could do about it. They now slide along the
edge they are on -- up and down at the side, left and right along the
bottom -- as one strip rather than five buttons, because they are one
control with five faces and letting them scatter would mean hunting for
one. Remembered per orientation, since a distance down the right edge
means nothing when the strip is lying across the bottom.

Two details that make it usable rather than merely possible: the travel
limits are measured from where the tabs actually ARE, not from the
numbers in the stylesheet, so adding or restyling a tab cannot leave the
strip able to slide off-screen; and a drag only becomes a drag after 4px,
so a plain click still opens the panel. The tooltip says it can be
dragged, added in JavaScript to all five rather than to five templates.

### A basket beside the menu took a screenful on a phone

The header zone stacks its sections, which is right for content and
wrong for two small controls: the menu and the basket each got a full
row, with a band of empty beside them. On a phone the site began most of
a screen down. The zone now lays those two out in a row.

### The newsletter editor had no text tools

The canvas was already the email -- written into in place, on the site's
own ground, in the site's own fonts. What it could not do was make a
heading, a bold word, a link or a list, which is most of what writing a
newsletter is.

The shape follows the FAQ's, deliberately: **a small written vocabulary,
escaped first and converted second** (`email_layouts.rich`). The owner
never types HTML; the toolbar writes `## `, `**`, `[words](address)` and
`- ` into the stored text, and `newsletter-editor.js` reads exactly that
back. Same trade as the FAQ, made for the same reason: the stored form
stays something a person can read, and no tag can arrive by being typed.

Four things this cost, each of which is the note worth keeping:

  * **The toolbar had to lose controls.** Alignment, a font picker and a
    colour picker are on the shared toolbar and mean nothing in an inbox
    -- every client that strips a stylesheet ignores most of them, and
    the vocabulary cannot write them down, so the serialiser would throw
    them away on save. A control that is discarded on save is a control
    that lies. `include_layout=false` turns that group off; the seven
    that remain are exactly the seven the vocabulary supports. (H3 was
    added to the shared toolbar for everybody -- the page and the blog
    wanted it too.)

  * **One dictionary of styles, read by both sides.** An email carries
    its styles on the tag, and `execCommand` emits a bare `<h2>`. So a
    heading made by the toolbar would have looked nothing like the one
    that gets sent -- in the very screen whose whole claim is that it
    shows you the email. `email_layouts.block_styles()` is handed to the
    page as JSON and the editor writes the same strings onto whatever the
    toolbar just made. Two hand-copied lists would have drifted.

  * **Rewriting the DOM fights the caret.** The first version tidied on
    every keystroke and scattered the words as they were typed
    ("We are open ate on Thursdays**l**"), because replacing an element
    moves the caret to the start of what replaced it. Split in two:
    writing a style attribute is safe and runs continuously; replacing a
    node runs on blur and before saving. And READING handles both forms,
    so what is stored is right at any moment regardless of which has run.

  * **A styled span is not a block.** `styleWithCSS` makes bold a
    `<span style="font-weight:bold">`, so the reader has to understand
    that form -- but a heading carries `font-weight:700` as part of the
    email's own style, and reading THAT as emphasis wrapped every heading
    in `**`. Only an inline span counts. Related: `insertUnorderedList`
    nests the `<ul>` inside the `<p>` it was made from, which is invalid,
    unreadable by the serialiser and puts the caret in front of the words
    already there. It is lifted out and the caret put back into it.

**Checked by driving it.** `tools/newsletter_editor_check.py` types into
the canvas, presses the toolbar buttons, saves, and compares what would
be SENT against what was on screen -- 18 assertions. It needs a browser
and a running instance because that is the only place the thing it checks
happens: a serialiser in JavaScript and a renderer in Python have to
agree exactly, and neither language can prove that alone. A drift between
them raises nothing; it just quietly changes what somebody wrote.

## A newsletter stopped being a set of slots (2026-08-27)

Asked for directly: buttons and pictures should be optional and come from
the toolbar; the template should be a dropdown in one toolbar; a template
should lay out boxed positions the writer can then replace and restyle,
background and font included.

Taken together those are not four adjustments to the fixed-slot model --
they are a different model, and the one this project already uses
everywhere else. A layout was a declared set of named fields, which meant
**a letter could never carry a picture and a story could never carry
two**. Every newsletter had exactly the parts its layout declared,
whether it wanted them or not. That is a page TYPE wearing a different
coat, and the answer is the one `PAGE_LAYOUTS` already gives for pages:
a layout is a **starting arrangement**, nothing more. A template seeds
the blocks; every one can be added, removed, moved or restyled
afterwards; and nothing later asks what a newsletter was made from.

### I had to take back something I told the user

I had turned alignment, fonts and colours off in the newsletter toolbar
and written that they "mean nothing in an inbox". That was too strong and
the user was right to push. Inline `background-color`, `color`,
`font-family` and `text-align` are standard HTML-email practice -- they
are attributes on a table cell, which is the one thing every client
renders. What actually fails is `@font-face` (Gmail strips it), CSS
classes and flexbox.

The rule I had reached for -- **a control that is discarded on save is a
control that lies** -- was sound; I had just misdiagnosed which half was
failing. Those controls lied because the STORED FORM was a flat text
field that could not record them, not because an inbox would ignore them.
A block can record them. So the test for admitting a style control is two
parts, and both have to pass:

  1. does an inbox honour it, and
  2. can the stored form write it down?

`EMAIL_FONTS` is real installed families only, for the first test.
`_clean_style` drops anything not on the list, for the second.

### The shape

  * `BLOCK_TYPES` -- heading, text, picture, button, divider. Closed, like
    `PAGE_TYPES`, and for the same reason: everything in it has to survive
    an inbox, which is a question with a fixed answer rather than a matter
    of taste.
  * **One template renders both.** `emails/blocks.html` is the email that
    is sent AND the canvas that is written into; `edit` is the only
    difference, and with it false not one extra attribute is emitted.
  * **One toolbar**, in four groups, in the order somebody works in: pick
    a shape, add things, write, style what you wrote. Alignment/font/
    colour sit in the block group rather than the writing group, because
    "make this word red" and "make this block red" are different acts and
    two controls that look alike but differ would be worse than either.
  * **Structure is saved and re-rendered by the server.** Adding, moving
    or restyling submits the form. Rebuilding the canvas in JavaScript
    would mean two renderers, and this screen's entire claim is that what
    is on it is the email. Scroll position and the selected block are
    carried across, so it reads as updating rather than reloading.
  * Old drafts still open: `from_named_slots` reads the previous shape as
    blocks. An upgrade that silently empties somebody's draft is worse
    than one that refuses to run.

### Four bugs worth writing down

  * **`tojson` in an attribute is cut at its first quote.** The blocks
    went into `value="{{ blocks | tojson }}"`; tojson escapes for a
    SCRIPT block, leaving the double quotes JSON is made of intact, so
    the browser ended the value at the first one and the field arrived as
    the two characters `[{`. Everything downstream then behaved quietly
    as though the newsletter had no blocks in it -- no error anywhere.
    `| forceescape` is the fix, and the tell is that a control which
    should act on N things acts on none.

  * **Re-reading the canvas by index, after moving something.** The
    submit handler reads each editable back into the block at the same
    position, which is right on Save and destroys the newsletter straight
    after a splice: the DOM still shows the old arrangement, so block 3's
    words go into whatever is at position 3 NOW. Every structural action
    collects first, then moves, then submits with the re-read skipped.

  * **`hidden` loses to a class.** The "where does this point" panel is a
    `.card`, and `.card`'s `display` beat the UA rule for `[hidden]`, so
    it stayed on screen for every block -- asking where a HEADING goes.
    Needs `.cms-issue-asides[hidden] { display: none; }` said explicitly.

  * **An invisible non-breaking space, again.** I wrote `/ /g` in a regex
    with a real U+00A0 in it. It works, and it is unreadable and
    unmaintainable -- the same class of fault as the literal backspace
    that cost a day earlier. Written out as ` `, and
    `email_layout_check.py`'s invisible-character sweep now catches a
    raw U+00A0 in `.py`/`.js`/`.css` (allowed in templates, where it can
    be a real typographic choice).

### One thing extracted rather than duplicated

The Media Library picker lived inside `inline-editor.js`, which only ever
loads on the public page -- so an admin screen had no way to ask for a
picture, and this one was about to grow a second picker. Pulled out to
`static/js/admin/image-picker.js` as `window.cmsImagePicker`, the same
move `modal.js` and `wysiwyg-commands.js` already are. It builds its own
markup, and uses the page's copy where one already exists.

**Checked by driving it**: `tools/newsletter_editor_check.py` is 35
assertions now -- it adds a button and a picture, removes one, moves a
block and checks its words moved with it, styles one and checks the
colour arrives on the cell of the SENT email, writes with the toolbar,
and changes the template (confirming that it asks first, and that what
gets laid out is what the server declares).

## The newsletter screen became a mail composer (2026-08-27)

Asked for: the toolbar, subject and recipients laid out like Outlook --
a recognised format -- with the template and tools along the top and the
recipients beneath them; Save and Schedule added; and "See it as it will
be sent" shortened to Preview.

The layout part is straightforward and the reason it is worth doing is
not aesthetic. The parts were all there already, in an order nobody would
choose: subject in a card at the top, **"who gets it" in a card at the
BOTTOM, beside Send**. So deciding who a newsletter was for happened
after writing it, on a different part of the page from everything else
about it. A composer's order -- tools, actions, To and Subject, then the
message -- is not a style, it is the order somebody actually works in,
and it is already in everybody's hands.

**One form, four `formaction`s.** That is what made the layout possible
rather than just rearranged. "Who gets it" was in a form of its own next
to Send; Schedule could not have reached it without a second copy of the
control, and two audience pickers that must agree is a bug waiting to be
written. Send and Schedule and Preview now carry their own `formaction`
and Save keeps the form's, so all four read the one field.

Send asks before it goes, because it cannot be taken back. Schedule does
not ask, because it can -- right up until it goes.

### Schedule had to be real, and that is the whole of the work

An option called Schedule that quietly never fires is the exact thing
this project's own rule forbids: a control that is discarded is a control
that lies. There was no scheduler here and deliberately so -- the Cal.com
note says building one is "the one thing this design deliberately does
not do", though that is about availability, not about a queue.

The hard part is not the clock. **This app runs two gunicorn workers
against one SQLite file**, so anything that wakes up looking for due
sends is running twice, and the failure it invites is mailing everybody
twice -- which you find out about from your readers. Every decision
follows from that:

  * **The claim IS the lock.** Taking a job is one UPDATE carrying the
    state it expects in its WHERE clause (`claimed_at IS NULL`), so
    exactly one worker's UPDATE can match and `rowcount` says which one
    won. No lock table, nothing to leak if a process dies mid-send: a row
    that was claimed and never finished is visible AS a claimed row, and
    can be reported rather than silently retried into a double send.
    Committed immediately, because the claim has to be visible to the
    other worker BEFORE this one starts the slow part.

  * **A failure is never retried automatically.** It is written down with
    its reason and left for a person. An automatic retry of "send to
    forty people" cannot tell "SMTP was briefly down" from "twenty of
    them already got it", and guessing wrong is the one failure here that
    cannot be taken back.

  * **The thread is armed by the first request each worker handles**, not
    at import time -- which is where it belongs by every other measure.
    gunicorn runs `--preload`, so `create_app()` executes in the master
    and the workers are forked from it, and **threads do not survive a
    fork**. One started there would sit in the master, where no request
    is ever served, and neither worker would have one. The consequence
    worth knowing: a site nobody ever visits does not send. Scheduling one
    is itself a request, so the poller is running from the moment there
    is anything to do.

  * **A scheduled send runs inside a request context built from the
    site's own address.** `url_for` cannot build a link without knowing
    what host to build it for, and a thread has no request to borrow one
    from -- this showed up as "Working outside of request context" the
    first time the checker ran it. The site's public address is the
    correct answer, since it is the address the unsubscribe link has to
    work at; and reading it first is also the check that there IS one.
    Without it the job is refused rather than sent with a link to
    nowhere.

  * **The guards were extracted before the caller was written**, which is
    what CLAUDE.md already said to do about `_send_it`. Is email set up,
    is there anything to send, is anybody on the list, is there a postal
    address -- all four now answer in plain data (`newsletter.preflight`
    returning `Ready` or `Blocked`), so the route flashes them and the
    scheduler writes them down, from ONE set of rules. `newsletter.deliver`
    is the other half. Neither knows about Flask.

  * **What goes is the current content, not a frozen copy.** Somebody who
    schedules a newsletter and then fixes a typo expects the fixed one to
    go. The subject is stored on the job as well, so the schedule can be
    read without opening what it points at.

  * **The clock is UTC in the database and local on the screen.** The
    offset comes from the browser rather than a setting, because the
    person typing the time is the one looking at that clock -- and it is
    re-read on every submit, not once at load, so a page left open across
    a daylight-saving change does not schedule an hour out.

### A quiet bug found on the way

`last.sent_count` -- the column has always been `recipients`. Jinja
resolves a missing key to Undefined and renders it as nothing, so "Last
sent … to 40 people" had been printing "to  people" for as long as it has
existed, on two screens. Nothing raised, nothing logged. It is the same
shape as the `tojson`-in-an-attribute bug from earlier today: a template
expression that is wrong produces emptiness, not an error.

**Checked by racing it**: `tools/schedule_check.py` (26 assertions) puts
a job on the clock, proves nothing goes early, has two workers claim the
same row and proves exactly one wins, sends it with the mail captured,
then breaks each precondition in turn and proves it refuses with the
reason written down rather than mailing anyway. The poller was also
watched firing on its own against the live container, arranged so the job
would be refused rather than sent.

## The picker could not tell two shapes apart (2026-08-28)

**Superseded within the hour: the picker was REMOVED** -- see "The shape
is chosen in the editor" below. `render(..., specimen=True)`, `sample()`
and the picker's CSS are all gone, so do not go looking for them. The
entry is kept because the lesson at the end of it is about checks and
outlived the feature, and because the sequence itself is worth reading:
the owner had already said the picker was not wanted, and I spent an
hour making its specimens distinguishable instead of taking it out.
Polish on something that should not have existed is worse than no polish
-- it makes the thing look considered.

Found by looking at a screenshot during a verification pass, not by any
check -- and it had been true since the layouts were built.

"A letter" and "One story with a picture" rendered IDENTICALLY in the
picker: a heading and a paragraph, in both. The cause is two pieces of
correct behaviour meeting. A picture slot with no picture in it is left
out of a real email, and a button with no address is left out for the
same reason -- "a button that goes nowhere is worse than none". A
specimen has neither, so the story lost both, and what was left was a
letter.

The entry that built this said, of the picker: "A name and a sentence
cannot show what a shape looks like -- which is the whole basis on which
one is picked." It was right, and the picker was not doing it. Two of
the four choices were the same picture.

`render(..., specimen=True)` draws those empty slots as plain plates, so
the ARRANGEMENT is visible. It reaches nothing else: with `edit` and
`specimen` both false, not one extra attribute is emitted, and
`email_layout_check.py` now asserts that all four specimens are
different shapes AND that a sent story carries no placeholder.

**Worth keeping as a lesson about checks.** Every existing check passed
throughout: each layout rendered, carried tables, avoided classes,
survived the wrapper. Nothing compared them to EACH OTHER, because
nothing had thought to -- and the fault was only visible as a
relationship between two outputs, not as a property of either. Some
faults are only visible by looking.

## Where this stands, and what is left (2026-08-27, end of day)
Everything the previous summary listed as "specified and unbuilt" is
built. What is below is either a decision waiting on the owner, or work
that has been named and scoped and not started. Nothing here is a fix
somebody forgot.

Built today, after that summary was written: the scheduled-sends list and
scheduled blog posts; the base currency (and the basket bug it turned
up); the wording editor for the four messages that send themselves; the
two shape variables; the template lifecycle with its fork question,
promotion and completeness check; the rate limit `captcha.py` had always
claimed; and the WhatsApp link. Each has its own entry above and its own
checker.


Written at the end of a long day on a live install, so the next person --
including me -- does not have to reconstruct it from thirty entries
above. Everything below is either specified and unbuilt, or a question
waiting on the owner. Nothing here is a fix somebody forgot.

### What is actually open

**Nothing.** All four remaining items were decided by the owner on
2026-08-28 and are recorded below with their reasoning -- including, in
each case, what would reopen them, because a decision without its
trigger is a decision somebody has to make again from scratch.

Nothing is waiting. What follows is the record of four decisions
and what would reopen each. Everything else in this
summary is a record of something built -- the sections below keep their
reasoning, which is the point of them, but none of it is waiting.

**Decisions, waiting on the owner. Not started on purpose.**

  * **A visitor-facing AI assistant.** ~~Open.~~ **DECIDED: not building
    it** (2026-08-28, the owner). A contact form that works beats a
    chatbot that guesses. The reasoning is worth keeping because it is
    the reason to REVISIT rather than the reason to refuse: the hard part
    was never answering, it was what the thing says when it does not
    know. A retrieval assistant asked "can I get a refund after 30 days?"
    about a policy the site does not carry will still produce something
    plausible, in the owner's voice, to their customer -- which is a
    commitment nobody made. Refusal-first ("I do not know, here is a
    person") is the small, safe shape, and it is what to build IF this is
    ever wanted. Against it either way: public attack surface needing the
    rate limiting the contact form now has, and per-conversation API
    cost on somebody else's traffic.
  * **The WhatsApp Business API.** ~~Open.~~ **DECIDED: the link is
    enough** (2026-08-28, the owner). A visitor taps and messages; the
    replies arrive in the WhatsApp the owner already has. Nothing to
    build, and the reasoning generalises past WhatsApp: the API is not a
    bigger version of the link, it is an INBOX -- approved sender,
    Meta-preapproved templates, an inbound webhook, a screen to read and
    reply, and all the state that implies (who answered, what is
    unanswered, what is resolved), plus per-conversation fees. It earns
    its place only if customer conversations are to be MANAGED inside
    this CMS, which is a decision about what this product is, not about
    which messaging service it speaks.
  * **Asking a buyer for their email as well as their link.** ~~Open.~~
    **DECIDED: no** (2026-08-28, the owner). The link stays the
    credential. Two reasons, and the second is the one that settles it:
    it is friction on somebody who has JUST paid, at the first moment
    after buying, which reads as distrust at the worst point in the
    relationship -- and it stops very little, because whoever holds the
    link almost certainly holds the inbox it arrived in. What it would
    mostly filter out is the buyer themselves, on a device where they
    cannot remember which address they used.

    The case that WOULD justify it, if it ever arises: selling files
    worth forwarding, where the link being shareable is the actual risk
    rather than a theoretical one. The optional page password already
    covers the case that needs more today.

**Named, scoped, not started.** Nothing. Both entries that stood here
are built; they are kept below with what building them turned up.

  * **Recurring fulfilment.** ~~Open.~~ **BUILT** (2026-08-28) --
    `invoice.paid` handled, `tools/subscription_check.py`. Three things
    it turned out to be about, only one of which this note had seen: the
    renewal itself; the FIRST payment, which arrives twice (as a checkout
    session AND as an invoice with `billing_reason: subscription_create`)
    and would have handed every new subscriber double what they paid for;
    and `WEBHOOK_EVENTS`, because a handler for an event nobody
    subscribed to never runs -- and an endpoint created before an event
    was added keeps its old list forever, so the Integrations screen now
    names anything Stripe is not sending it. A cancelled subscription
    needs nothing: the period was paid for, so the credits stand.
  * **The compose ribbon is dense.** ~~Open.~~ **IMPROVED, and measured
    rather than estimated** (2026-08-28). It was worse than this note
    said: four rows at EVERY width, not just on a narrow laptop, because
    the bar is 852px inside the admin's content column rather than the
    1440 the window suggests. Three deliberate rows now -- the two "what
    you are making" groups together, then the writing tools, then the
    selected block's style. Getting to two means moving that group's
    move/remove buttons onto the selected block in the canvas, which is
    arguably where they belong but is a change to how the editor is
    USED, not a layout tweak. ~~Left for somebody to ask for.~~

    **CLOSED** (2026-08-28). Move and remove ARE on the block now -- not
    for the row count, but because an owner reported being unable to
    remove a block at all: the buttons were in a group that is dimmed
    until you select something, which is a control nobody finds. It is
    still three rows, and the prediction that it would reach two was
    wrong, because the same change added a Link field to that group.

    What the measuring found instead was worse than density and is
    fixed: the bar was **163px with nothing selected and 122px once a
    block was clicked** -- it got SHORTER when you selected something,
    so it changed shape as it was used. Two causes, both width. The
    label saying which block the controls act on swung 57px between
    "Nothing selected" and "Words 2" (fixed width now, and "No block").
    And the Link field was HIDDEN when it did not apply, taking the
    group from 490px to 713px the moment a button was chosen -- so it is
    dimmed instead, which is the rule the CSS three lines above already
    stated for every other control in that group and for exactly this
    reason.

**Named, measured, DONE** (2026-08-28).

  * **256 controls with no tooltip** — now none. Mostly the editor's own
    tool panels: the Menu tool's page checkboxes and its two link
    builders, the Embed tool's code editor and Save HTML, the colours
    panel, and a dozen Save buttons that all said "Save" and none of
    which said WHAT they saved. Each now names its own consequence,
    because "Save" is the label and the consequence is the half a label
    cannot carry.

    Two things made it tractable, and both were fixes to the audit rather
    than to the app. It reported "input:checkbox (no words)" 72 times,
    which is true and unactionable — it names none of them; every
    finding now carries its nearest classed ancestor, which is what a
    person greps for. And it had to be taught three exclusions first, or
    the real ones were buried: a `hidden` file input is machinery behind
    a button that carries the sentence, an aria-hidden control is
    deliberately not announced, and a control with a VISIBLE text label
    is already explained — which is the whole reason the rule exists.

**Nothing to run either.**

  * **The four duplicated pictures on the live install.** ~~Open.~~
    **CLOSED** (2026-08-28, the owner): that install is to be destroyed
    and reinstalled, so they go with it.

    Worth recording WHY that is a real fix rather than a deferral: a
    fresh install measures 0 wasted (`tools/media_check.py`), so those
    four were an artefact of that install's own history -- format
    changes, renames, a cleanup that trusted names instead of bytes --
    and not something the code produces. Reinstalling therefore removes
    the cause and not just the symptom.

    The tool remains, and it now tells apart the two cases that look
    identical to a name-based check: two TEMPLATES holding the same
    picture is correct and must not be "fixed" (a template's pictures
    belong to the template; a shared folder is what once made an
    exported package arrive empty), while two copies in one place is
    waste.

Also parked, deliberately, in CLAUDE.md's own "Deferred follow-ups"
rather than here: standalone colour palettes, a saved-section pattern
library, and unifying the AI Theme Generator with Template Packages.
Those are architecture set aside, not work owed.


### Answered and built since this was written

**The transactional emails are dressed.** Answered by the owner:
"Dressed". `newsletter.to_transactional_html()` renders them in the
site's own look with no unsubscribe footer, since a receipt is not a
mailing.

**The email layouts are built, wired, and then rebuilt.** They shipped as
four fixed sets of named slots; that model is gone. A newsletter is an
ordered list of BLOCKS and a layout is a starting arrangement of them --
see "A newsletter stopped being a set of slots" above for why the fixed
slots had to go, and "The newsletter screen became a mail composer" for
the screen that uses them. `templates/emails/layouts/` no longer exists;
one template, `emails/blocks.html`, renders both the sent email and the
canvas it is written in.

**Send later exists.** `services/scheduling.py` plus
`tools/schedule_check.py`. The claim is the lock, because two workers
wake up together.

### Loose ends from that work

**Nothing lists what is scheduled.** ~~Open.~~ **BUILT** -- a table on
the Newsletters screen: what is waiting, what is going out right now
(and so can no longer be recalled), what went, and what did not go and
why.

**Only newsletters can be scheduled.** ~~Open.~~ **BUILT** -- a post
goes on the same clock, from the row it is already sent from, through
one booking routine so the two sets of refusals cannot drift apart.
Scheduling a draft does not publish it; going out does.

**The compose ribbon is dense.** STILL OPEN. Four groups fit at 1280px and wrap to
two rows on a narrow laptop. Legible, but worth a second look once
somebody has used it in anger -- the likely answer is that the block
style group collapses behind one button until a block is selected.


### Specified, agreed -- and now built (2026-08-27)

**The fork, and the template lifecycle.** ~~Specified, not built.~~
**BUILT** (2026-08-27) -- `services/lifecycle.py`,
`tools/template_check.py`. Built as the three entries below work it out,
with the open question answered and one thing found that none of them
anticipated:

  * **The open question, answered.** `_retire_foreign_pack_pages` deletes
    any page whose `source_template` differs from the newly-activated
    slug -- and an edited page still carries the slug it arrived with, so
    switching template threw the owner's work away and reported only
    "removed 4 pages". The fork was never protecting it, as suspected.
    The fix is `pages.owner_edited`, set by a TRIGGER on `sections`
    rather than by every save path remembering to: a dozen places write a
    section, and one of them forgetting would be a page silently deleted
    months later. Load Content clears it, because putting the pack's own
    copy back is exactly the act that un-edits a page. The flash now says
    what it SPARED, which is the more surprising half.
  * **The guard is a named SET, not a decorator on each route**, and that
    is about the seventeenth route rather than the fifteen that exist. A
    set can be checked against the routing table; a decorator that
    somebody forgets cannot. `template_check.py` found one on its first
    run -- `template_shades_reset` -- which is the entire argument for
    doing it that way.
  * **Not anticipated**: what to do about a source that is not ACTIVE. A
    fork is "give this site its own copy of what it is running", so
    changing the look of an inactive source has nothing to fork into. It
    is refused outright, and told to activate it first.

The three entries below are kept as written, because they are the
reasoning rather than the record.

**The fork, and the template lifecycle** (original entry). Three entries
above work it out: content edits never fork (the automatic trigger IS now removed),
changing a LOOK on a source asks first, the owner names the copy,
overwrite-or-new when one exists, and a finished custom template is
promoted to a source -- which is also the moment it gets packaged and
becomes exportable. Two things to settle while building: a promoted
template has no zip behind it and needs its own flag rather than
borrowing `is_builtin`, and promotion should be reversible until
something depends on it. Note this supersedes CLAUDE.md's "exporting
stays an always-available action on any library entry".

**An editor for the other site emails.** ~~Not built.~~ **BUILT**
(2026-08-27) -- `services/site_emails.py`, Email -> Message wording.

Built as specified, and the one thing worth adding is why the split
landed where it did. The tempting version gives the owner the whole
message; the right one gives them a greeting and a sign-off around a body
the code renders, and the reason is the sign-up form's rule generalised.
That line ("a confirmation email is coming") is fixed because an owner
rewording it into "you're subscribed" would make the site lie about its
own mechanism. Every fact in these four messages is the same kind of
thing: what actually happened, or what the reader needs in order to act.
An owner writing AROUND them is adding their voice; an owner writing OVER
them is deleting something somebody needs, usually without meaning to. So
there is no field that can.

Two smaller decisions: a placeholder this app cannot fill is left visible
as `{{whatever}}` rather than becoming a blank -- a visible mistake gets
fixed and a gap does not -- and the placeholders are clicked in rather
than typed, because `{{ site }}` with spaces does not substitute and what
arrives is the literal braces. The newsletter's own greeting and sign-off
stayed on the Newsletters screen: that is where somebody is standing when
they think about them.

**Currency.** ~~Three separate features that keep being asked for as
one.~~ **The base currency is BUILT** (2026-08-27). Regional detection
and a converter remain, and remain separate.

Worth recording what building it turned up, because the reason for doing
it was stated as tidiness and the real reason was money. `cart.lines()`
took the FIRST line's currency and added every later amount into one
subtotal regardless -- so a basket holding 10 CHF and 10 EUR read
"20.00 CHF", a number that is not a price in either currency, and the
customer was quietly quoted the wrong thing. Nothing raised. The
per-product dropdown (CHF first in the list) was the mechanism, so it is
gone rather than defaulted: a new product takes the site's currency, an
existing one keeps its own because a Stripe price is immutable and a
reprice in a new currency would orphan the fulfilment rule keyed to the
old, and anything on sale that disagrees with the base is named on the
screen. `shipping_for` also had a hardcoded `"chf"` fallback, so a shop
charging in euros quoted postage in francs. `tools/currency_check.py`.

### Gaps found by using it -- built (2026-08-27)

**A template's shape, and a claim I got wrong.** I recorded that a
template cannot carry its own shape. It can, and always could: all
sixteen manifests declare `shape_override`, `install_theme_package`
writes it, and forking copies it. What I had actually seen was a site
whose Corners control had been set to Auto, which is a different thing.

The real gap was narrower and is now fixed. `shape_override` is BOTH the
shipped shape and the Corners control's own value, so choosing Auto
erased what the template was designed with and nothing remembered it --
a site that arrived pill-cornered simply stopped being one, with no way
back short of reinstalling. A template's shipped shape and shadow are now
recorded separately (`shape_default`, `shadow_default`, written on every
install because they are the package's statement about itself), and Auto
falls back to them. Auto now means "this template's own look", which is
what an owner reads it as.

Worth keeping the mistake as well as the fix: I diagnosed a missing
feature from one observation of a live site, and wrote it down as fact.
The setting had been changed. Reading the code would have taken a minute.

**A short wide box needs an inline-only inset.** ~~Not built.~~ **BUILT**
(2026-08-27) as `--site-radius-pad-row`: the vertical half is a length,
the horizontal half stays a percentage because horizontally it is
measuring the right thing. Applied to the three surfaces that had been
left with their own padding -- the file card, the account flash and the
sign-up note.

**`clamp()` cannot cap a lens or a blob.** **BUILT** (2026-08-27), and
the diagnosis in this entry was half right in a way worth correcting.
"The declaration is invalid and it is dropped" suggests the previous
declaration wins, which is what happens to a mistyped LITERAL. Through
`var()` it does not: the browser accepts the declaration, substitutes,
and only then finds it invalid -- "invalid at computed-value time",
which means UNSET. Measured in a browser: `clamp(0px, var(--lens), 28px)`
computes to `0px`. So the rule was not merely failing to cap, it was
removing the radius entirely, and on a gentle site it was silently
overriding a shape the owner had chosen. `--site-radius-safe` is always a
plain length. `tools/shape_check.py` measures all eight shapes and
carries a self-test that reproduces both old faults, because a check that
cannot fail passes everything.

### The small ones, and where each landed

  * **Duplicated pictures**: `tools/media_check.py` reports them by BYTES
    now, and tells the two cases apart -- two TEMPLATES holding the same
    picture is CORRECT and must not be "fixed" (a template's pictures
    belong to the template; a shared folder is what made an export
    silently incomplete), while two copies inside one template is waste.
    On a fresh install: 2 shared, 0 wasted. Run it against the live
    install to find the four.
  * **The "Added" moment on a Buy button** -- stale, and worth keeping as
    a correction. It reads `.cms-action-btn.is-added`, which is `#15803d`,
    a success green; a Buy button carries BOTH `cms-buy-btn` and
    `cms-action-btn` (`sections.py` says so where it builds the markup),
    so the rule matches and it is already green. Nothing to fix. Reading
    the CSS would have taken a minute -- the same mistake as diagnosing a
    template's shape from one look at a live site.
  * **A responsive preview** -- built. The dropdown is in the admin bar
    (`public/page.html`); it showed nothing until the framing headers
    were fixed, which was a separate bug.
  * **Protecting a purchases page further** -- asking for the buyer's
    email as well as the link. Designed, refused so far because it puts
    friction on somebody who has just paid.

### Carried from before today -- two closed, two not

**The CAPTCHA is closed, and not the way this note expected.**
"Arithmetic stops nothing that matters" is true, and `captcha.py` already
said so in its own last paragraph: the sum is not meant to stop a
determined attacker, "the rate limit on the route is what bounds the
damage". **That rate limit did not exist.** The only limiter in the app
guarded the password on a purchases page. So the honest gap was never the
sum -- it was a module documenting a defence it did not have, which is
worse than documenting none, because it is the reason nobody went
looking. Built as `services/ratelimit.py` + `tools/abuse_check.py`.

Building it turned up something this note had not seen: the SIGN-UP form
had no check at all, and it is the more dangerous of the two. The contact
form mails the owner; a flood is a nuisance in their inbox. The sign-up
form mails whatever address is typed into it, so a flood is a
confirmation message sent to a stranger who did not ask, at an address
the attacker chose -- somebody else's inbox, and this site's reputation.
It has the tighter allowance now, and the same honeypot, deliberately
using the same field NAME, so a bot that has learned to leave `website`
alone on one form has learned it on both.

**WhatsApp: the half that was a task is done, the half that is a decision
is not.** The note said "a `wa.me` link is an afternoon". Looking at it,
most of that afternoon was already spent: a `wa.me` address is `https://`,
so it passes `BUTTON_SCHEMES` and an owner can paste one into a Button or
a Menu item today. No tool was needed and none was added.

What they cannot be expected to know is the NUMBER. wa.me takes the full
international number and nothing else -- no plus, no spaces, no dashes,
no brackets, no leading trunk zero -- and a number with any of those in
it produces a link that opens WhatsApp to nobody, with no error and
nothing to see. So `legal.whatsapp_link()` formats it from the number the
site already has, and the Legal screen offers the result to copy. It
REFUSES a local number rather than guessing a country code: guessing
produces a link that reaches somebody, just not the right somebody, which
is the worst outcome available.

Still open, and genuinely a decision rather than a task: the WhatsApp
Business API -- whether this product holds customer conversations at all
-- and a visitor-facing AI assistant that has to start from refusal
rather than retrieval. Both are written out above and unchanged.

### Should the featured image live in the text toolbar? (asked 2026-08-27)

Asked when the blog editor got the shared toolbar. The answer is no, and
the reason is worth stating because the two look alike:

  * An **inline image** is a picture inside the words, inserted at the
    caret. The toolbar acts on a caret; that is what a toolbar is for.
  * A **featured image** is the picture that REPRESENTS the post -- on a
    Blog tool's cards, in a listing, at the head of the post. It is a
    property of the post, and it has no caret to be inserted at.

One button for both would leave nobody able to say which they had just
set. They are different questions asked of the same file.

**But the complaint underneath is fair, and there is a real defect in
it**: the Featured Image card is wrapped in `{% if post %}`, so it does
not exist while the post is being written -- you must save first, then
scroll to a separate card at the bottom, choose a file and press a second
Upload button. Three of those four steps are avoidable. Worth doing:
bring it up beside the title where it belongs, let it be set while
writing rather than only afterwards, and make it one control rather than
a form of its own.

### The newsletter, wired; the receipts, dressed (2026-08-27)

Both halves of the question above, answered by the owner: dress the
transactional mail, and wire the layouts up.

**Wired.** A newsletter is now a thing of its own -- a `newsletters` row
holding a layout and the words filled into it, at
`/admin/newsletters/issue/...`. Pick a shape from four cards (a name in a
dropdown cannot show what a shape looks like), fill the slots the layout
declares, preview exactly what will be sent, send it. The send path is
the one pages and posts already used, unchanged: a layout's body is one
HTML section, which is what `sections` has always been.

Two details worth keeping. The values are JSON because the slots differ
per layout and a column each would be a migration every time somebody
adds one. And a send is refused BY NAME -- "Fill in a subject, Button,
Button goes to" -- rather than by a generic complaint, because the point
of a refusal is to say what to do.

The URL space needed care: `/newsletters/<int>` already belongs to
sending a PAGE, so these live under `/newsletters/issue/`. A blanket
rename to get there also caught `newsletter_send_post` by substring and
turned it into `newsletter_issue_send_post`, which the screen then failed
to build a URL for -- a reminder that a rename across templates wants a
list of endpoints, not a string replace.

**Dressed.** All four transactional messages now carry an HTML half:
the order confirmation, the sale notice to the owner, the confirmation
invitation and the welcome. Same card, ground, colour and font stack the
newsletter gets.

`to_transactional_html` is deliberately NOT the newsletter's wrapper, and
the difference is one paragraph: a newsletter says "you are getting this
because you asked us to" and carries an unsubscribe link, because it is a
message to a list. **An order confirmation is not.** There is nothing to
unsubscribe from, and offering it would invite somebody to opt out of
their own receipt. The welcome mail keeps its unsubscribe because that
one IS a list message -- and it already had it in the words, so the shell
only dressed what was written.

The words come from the plain text each message already had, converted to
paragraphs, so there is one wording to keep true and the text half is the
same words rather than a second draft that can drift.

`tools/signup_check.py` was capturing `mailer.send` and these now call
`mailer.send_html`, so it attempted a real SMTP login and reported the
whole signup flow broken. The checker captures both now -- worth noting
because it was a checker that failed, not the thing it checks, and the
output looked identical either way.

### The four small ones, and a preview that does not lie (2026-08-27)

  * **The duplicate pictures resolved themselves.** The live picker fell
    from 154 files to 77 once the stale-PNG cleanup ran. Two duplicates
    remain and are correct: the same picture in a builtin and in a saved
    copy of it, which is the design -- a template's pictures belong to
    the template, and de-duplicating across them would break that.
  * **"Added" is green now**, not `--primary-dark`. On an orange site the
    site's own colour gone darker reads as the button being pressed, not
    as success. This is one of the few things a site should not restate in
    its own palette.
  * **Protecting a purchases page further is already done**, by the
    buyer's own optional password. The item predated it and described the
    weaker version -- asking for their email as well as the link. A
    password they choose is strictly better: it is something they know
    rather than something they were told, and it is opt-in rather than
    friction on everybody. Closed rather than built.
  * **The responsive preview is a frame, not a narrowed page.** The
    obvious implementation squeezes the page into a 390px column, and it
    lies: a media query answers the VIEWPORT, so a page pushed into a
    narrow box on a wide screen still lays itself out as a wide one and
    shows the wrong thing confidently. It loads the page in an iframe at
    the chosen width instead, where the queries fire exactly as they will
    on a phone.

    That needed `?preview=1` -- one request rendered as a visitor sees it,
    without touching the session, so the editor stays open behind the
    frame. It clears `logged_in` as well as `editing`, because the admin
    bar is drawn for anyone signed in and a preview showing a strip no
    visitor will ever see is not a preview.

### The admin becomes buttons and tabs; the Library stops lying (2026-08-27)

**The Dashboard was six long sections on one screen** -- blogs, settings,
pages, the theme generator, templates, layout -- and it read as a wall.
It is a row of buttons now. The sections became screens: **Blog** on its
own (a list of things you write is not a setting), and **Design** with
tabs for Pages, Templates, Layout and the Theme Generator, the shape
Commerce and Email already had.

The markup did not change, only where it is rendered: each section is a
partial under `partials/dash/`, and five thin routes share one
`_screen_context()`. That fetches a little more than any single screen
needs, which is the right trade against four query sets that drift.

One thing the split caught, and it is the usual shape: a macro import sat
in the GAP between two blocks, belonging to neither, so the Layout screen
raised `'nav_layout_diagram' is undefined`. Cutting a template into
pieces has to account for what lives between the pieces.

**The Media Library said "Nothing here yet" on a site with 77 pictures.**
It listed uploads only, and on a site whose pictures all came with its
template that is an empty screen headed Media Library -- which reads as
"you have none" while they are on disk and on the page. It now lists
every installed template's pictures too, 80 items where there were 0.

They are shown and **locked**, which is the honest pair: on screen
because somebody looking for a picture should find every picture, locked
because each belongs to a template that would be left with a hole in it.
A padlock rather than a missing button, so the reason is visible. And the
delete route refuses them rather than trusting the screen to hide the
control -- it takes a bare filename and looks in the uploads folder, so a
template picture sharing a name with an upload would otherwise have
deleted the upload instead.

**Help was describing an admin that no longer exists** -- "Dashboard →
Site Settings", a Templates section on the Dashboard -- and still said a
newsletter "really is a different kind of page" that "stays out of your
navigation", which stopped being true twice over: a page is in a menu
because somebody ticked it, and a newsletter is not a page at all any
more. Rewritten against what is actually there, including what a template
picture's padlock means and why a receipt carries no unsubscribe link.

### A phone cannot hold an ellipse (2026-08-27)

Reported from a real phone: pricing spills, blog entries sit against the
edge, the newsletter sign-up spills, the menu is a wide empty bar.
Measured at 390px, all one cause.

`--site-radius-pad` is percentages of WIDTH. That is right for a block
roughly as tall as it is wide, and it fails at both extremes -- a short
wide row was already known. A phone makes everything the OTHER extreme:
a newsletter block was 190x471, an ellipse of semi-axes 95x235, with its
words **3.05 times outside its own curve**. A blog card had `padding: 0`
and never inset at all.

**Padding cannot fix it, and trying proves the point.** Adding vertical
padding makes the box taller, which makes the ellipse taller, which
pushes the words further out at the ends. Measured: +92px of padding
moved 3.05 to 2.49. It chases its own tail.

So the strongly-curved shapes now state a small-screen radius as well
(`radius_small`), and below 700px they become firmly rounded corners.
Same judgement as the video and textarea caps: at that size the shape
stops the thing working. It is emitted with the rest of the shape rather
than from site-base.css, because that stylesheet is loaded BEFORE the
theme's own block and a media query in it would lose at equal
specificity.

The width is the bigger win. Those insets were eating half the screen:
every box went from 190px wide to 284px, and the words with them. The
menu strip went from a 342px bar holding one glyph pushed right, to
112px, centred.

### Two things that had never worked

**"Layout only has menu items."** The sidebar and footer pickers are
gated on `{% if active_tpl %}`, and `active_tpl` was computed in the
route and never passed to the template. Not a regression from splitting
the Dashboard -- `git` shows it was never in the context, so those two
groups of controls had never rendered for anybody. Twenty-seven picker
buttons where there were nine.

**A picker that only names things** asks somebody to imagine the answer.
The newsletter layouts were four names and a sentence each, and what a
shape looks like is the entire basis on which one is chosen. Each card
now shows the REAL layout, rendered with real sentences and scaled down
-- not a drawing of it, which could drift from the thing itself.

And the editor shows the email beside the words as they are typed. The
preview route answers the FORM rather than what was last saved, and
stores nothing, so the right-hand side is what would go out if you sent
it now -- and a half-written sentence never becomes the saved copy.
Writing into a column of text boxes and pressing Preview afterwards is
guessing with an extra step.

### The control was there, and unreachable (2026-08-27)

"I don't see the preview dropdown." It was on the page -- confirmed in
the live HTML -- and on a phone it was off the right-hand edge.

The admin bar is one `nowrap` row that scrolls sideways. Measured at
390px: **869px of controls in 390px of bar**, so five of its seven were
off screen, including the mode switch, the page picker and Preview at… .
A sideways scroll inside a fixed 47px strip is not something anybody
finds, and nothing on screen suggests there is more.

It wraps below 900px now -- **900, not 760, because the breakpoint is the
content's own width and a tablet at 768 was still losing two of them.**
Nothing off screen at 390, 768, 1024 or 1400.

**And the bar is sticky rather than fixed.** Fixed needs the body to
reserve exactly the bar's height; it reserved a hard-coded 40px against a
bar 47px tall, so seven pixels of every page have always sat underneath
it -- on every screen, since long before today. Wrapping made that worse,
because a wrapped bar's height depends on how many rows it takes and no
constant can know that. Sticky takes its own space and still stays put
while scrolling, which is what fixed was wanted for.

The lesson is about the report, not the bar: "I can't see X" was true,
and X was present, styled and working. Checking that it renders answers a
different question from whether anybody can reach it.

### The view IS the editor (2026-08-27)

Two attempts short of what was asked for. First a column of text boxes.
Then the same boxes with a live preview beside them -- better, and still
wrong: it asks somebody to hold two things in their head and look between
them. The ask was plainer than either. **Write into the email.**

`email_layouts.render(..., edit=True)` returns the SAME email with its
slots opened up: each one named, its words editable in place, and the
empty ones drawn so the shape can be seen before it is filled. The editor
page is that, in a card the width of the real one, on the ground colour
it will have in an inbox.

What makes it safe to do this to something that has to survive email:

  * **With `edit` false, not one extra attribute is emitted.** The slot
    names go only to the editor -- they were briefly emitted always,
    harmless in an inbox and still wrong to ship.
  * **The route that saves it never learned any of this happened.** A
    hidden input per slot is kept in step, so the form still posts
    `heading`, `body`, `button_url` exactly as when they were text boxes.
  * **The serialiser is the exact inverse of `paragraphs()`** -- that
    turns blank-line-separated text into `<p>` blocks, this turns them
    back. Written down in both places, because if one changes and the
    other does not, a newsletter stops reading back the way it was
    written. Same rule the FAQ editor already follows.

Three details that decided themselves once the canvas existed:

  * **An empty slot is drawn, not hidden.** A picture frame saying "click
    to add a picture" is how somebody learns the shape HAS one. Sent, it
    appears only when filled.
  * **What an email cannot hold moves under it.** Where a button points
    and where a picture lives are not part of the message, so they sit
    beneath the canvas rather than floating over it.
  * **The footer is shown, greyed, and marked as not theirs.** Leaving it
    off would make the email being written a different length from the
    one that arrives; making it editable would let somebody delete the
    two things the law requires.

Pasting is forced to plain text, because a paragraph copied from a web
page brings its fonts and colours with it and an email that half matches
the site looks like a mistake.

### A basket that costs no room, and a phone that starts at the top (2026-08-27)

**The basket can float.** Two new positions pin it to a corner of the
viewport, over the page, following the reader down it. In the flow it
takes a whole row of its own -- fine on a wide screen, and on a phone it
was 52px of a 150px header before any of the site appeared. Floating, it
takes none. Fixed to the viewport rather than to the header, because a
basket that scrolls away is a basket somebody has to go looking for; and
the section it came from is hidden with it, or a floating basket leaves
its own empty row behind. While EDITING that section stays visible --
you cannot click a tool that is not there.

**And the phone header was taking a screenful.** The site began 159px
down: 36px of zone padding, a menu strip, the basket's row. Tightened to
128px, and 77px with the basket floating -- less than half.

### One place to add a picture (2026-08-27)

A blog post's picture was a card at the BOTTOM of the editor, wrapped in
`{% if post %}` so it did not exist until the post had been saved once,
with an upload form of its own. Three steps and a scroll to add one
picture, and the picture appeared nowhere near where it would appear.

It is the toolbar's Image button now, and the picture shows immediately
under that toolbar -- which is where it sits in the published post, above
the words. It saves with everything else rather than through a second
form.

The shared toolbar learned one hook for it: `onImage`. Without one, an
uploaded picture goes in at the caret, which is what a page needs; with
one, the caller says what a picture is FOR. That is the same seam the
toolbar already uses for "which editable" and "what now" -- a caller
passes only what genuinely differs.

I argued against this earlier, on the grounds that an inline image and a
post's own picture are different things. They are, and the owner was
still right: there is one Image button in front of somebody writing a
post, and what it should do is the obvious thing.

### Taking things off again (2026-08-27)

Two removals, and they are not the same kind of act.

**A post's picture** now comes off from where it went on: a Remove
control on the picture itself, under the toolbar that set it. Nothing to
weigh -- a picture the owner does not want is simply not the post's
picture, and the file stays in the Media Library either way.

**A line from what has gone out** is different, and the confirmation says
so rather than asking "are you sure": *this line is how you would answer
"you emailed me" later, and nothing else keeps it*. The send record
deliberately outlives the page or post it came from -- that is why it
carries no foreign key -- so removing one is a per-row act, not a Clear
History button. The same distinction the subscriber screen already draws
between unsubscribing somebody and erasing them.

It touches nothing about anybody's subscription or consent. Those live on
`subscribers` and answer a different question: whether you were allowed
to write to somebody is not the same as whether you did.


## Adding was easy, taking away was not (2026-08-28)

Three faults from one message, and the first two are the same fault seen
from two sides: **everything in this app could be added and not removed.**

### A block could be added and not removed

The newsletter toolbar could put a button, a picture, a divider into a
newsletter. Nothing could take one out. The toolbar was the wrong place
to fix that -- a Remove button up there has to say what it will remove,
and the answer is a sentence ("the block you last clicked"), which means
reading before acting.

So the control is **on the block**: choose one and a small handle appears
over it carrying up, down and a red ×. What you are about to remove is
the thing you are pointing at.

Building it found something worse, and it had been there the whole time:
**nothing could be selected by clicking at all.** Selection only ever
happened via focus, so it looked like it worked in the cases anyone
tried. Watching the real event sequence:

    mousedown:H2   focusin:H2   mouseup:P   click:TBODY

A `click` fires on the **common ancestor of where the button went down
and where it came up**. Press inside a heading, release a pixel lower in
the paragraph beneath, and the click resolves to the `TBODY` they share
-- which carries no `data-block`, so the handler deselected whatever
focus had just selected. Selection is on `mousedown` now, which is the
event that knows where you actually pointed.

The handle made it worse before it made it better. Appending it *into*
the cell moved the DOM mid-gesture: the block shifted under the pointer
between press and release, so mouseup landed somewhere else and the
click resolved even further up the tree. The handle was destroying the
selection that created it. It is parented to the canvas and positioned
over the cell -- which is also the rule that was already there for a
different reason, since nothing that is not the email may live in that
table.

### A newsletter could be written and not thrown away

Nine of them accumulated on this install, all called "Untitled", all
mine. Each row in "Yours" has a delete now. The interesting half is what
it takes with it: a **scheduled send** pointing at a deleted newsletter
is not dangerous -- the poller finds nothing and says so -- but it leaves
a row on the "going out on its own" table promising something that
cannot arrive, which is worse than either sending or not. What it does
NOT take is the record that forty people were emailed. That record
carries no foreign key precisely so it can outlive its subject.

### Message wording described the message instead of being it

Two textareas and a collapsed preview, which asked somebody to hold three
things at once: what they were typing, where it would land, and what it
would look like there. These are the same kind of thing as a newsletter
and should not need a second screen learned.

It is the message now -- on the site's own ground, in the card it
arrives in, the owner's greeting and sign-off written into directly and
the code's own words greyed and inert between them. The grey is not
decoration: it is the difference between what you may change and what
you may not, said in the one way that needs no label.

And then said in words anyway, under each message. Grey carries it for
somebody who notices grey; a person who does not should not have to
hover over the text to find out which half is theirs.

The rule underneath is unchanged and is the reason the middle is inert:
the facts are not a field. What was bought, the link back in, what
somebody agreed to, the sender line. An owner writes around those.

### A checker that runs nowhere

`stale_media_check.py` read `app/data/templates/` -- the authored
folders, which the packager stage turns into zips and **deletes**. So it
could not run in the runtime image, and the host has no Flask. Its own
docstring said `python tools/stale_media_check.py`, which was true on no
machine. It unpacks a shipped zip when the sources are absent: the same
bytes that folder built, so the same starting point.

`newsletter_check.py` had a hand-maintained total (`67 checks`) that
would have quietly become a lie the moment anyone added one. It counts.

Two smaller things worth writing down, both about the shell rather than
the app. `docker compose exec -T web rm -rf /app/tools` does nothing on
Windows: Git Bash rewrites the bare `/app/tools` argument into a Windows
path, so the delete misses and the next `docker cp` **nests** into
`/app/tools/tools` -- and the checkers keep running, against the old
copy. Container-side paths go inside `sh -c '...'`. And a directory
named `templates;C` had been sitting in `app/data/` for days, empty,
copied into every image build: the same mangling, leaving debris instead
of silence.

## The pill under the menu (2026-08-28)

The owner's second report of the same fault, and the second report was
right both times.

A basket set to float is lifted out of the page and pinned to a corner.
The section it came from then holds nothing, and an empty section that
still paints is a placeholder sitting in somebody's header. Fixed once,
in the wrong scope; reported again.

    .cms-editing .cms-section:has(.cms-basket-align-float-top) > .block-html

That rule is correct and it is why the placeholder went away **while
editing** -- which is where I was standing when I found it. A visitor got
none of it. Measured on the live page, a visitor's header still carried:

    .cms-section   display=contents   0x0
    .block-html    display=block      30x18   bg=#fcfbf7
                                              border=1px  radius=999px

Two separate mistakes, stacked.

**The box inside the box.** `display: contents` was put on the section
and the section alone. `.block-html` is a different element and kept
being a box -- it pads `8px 14px` around a link that is `position:
fixed` and therefore contributes no size at all, so the padding is the
whole thing. A 30x18 pill wearing the site's card background, its border
and its 999px radius. Exactly what the screenshot showed.

**The scope.** The rule I needed already existed, four rules down, under
`.cms-editing`. I had written it. Scoping a fix to the surface the bug
was reported on is not a fix, and the visitor is most of the people who
will ever load the page. It is unconditional now and the editing-only
copy is gone -- two rules saying the same thing is the drift this project
keeps warning about, and here one of them was silently narrower.

Worth naming the trap under both, because it has now been hit three
times on this one element: **`display: none` on a box that contains a
`position: fixed` child hides the child too.** Fixed positioning escapes
the flow, not the display tree. Written as `none`, the placeholder goes
and so does the basket -- the fix removes the feature. `contents` removes
the box and keeps the child.

### A C1 control character, and a sweep that could not see it

While reading that rule I found the admin's own explanatory text was
`"This basket floats \x814 look for it in the corner"`. That is U+0081
followed by `4` -- an em dash that has been through a cp1252 round-trip.
It shipped, invisibly, into a message shown to the person editing.

`email_layout_check.py` has swept `app/` for control characters since one
cost a day. It tested `ord(c) < 32`, which is C0 only. U+0081 is in the
C1 range, 127-159 -- which is precisely the range a mangled encoding
produces, so the sweep was blind to the most likely way one arrives. It
covers both now and names the file and the codepoint.

### A net under it, and proof the net works

`tools/basket_check.py`. It puts a real basket on a real header, sets it
floating, measures in a browser, and takes it away again. Only a browser
can see this: the markup is identical either way and the server is
perfectly happy in both.

Both guards were checked by breaking them on purpose. Restoring the
editing-only rule: `it leaves no box behind it at all FAILED  block
30x18` -- the pill, by name. Writing `display: none` instead of
`contents`: `the basket is still on screen FAILED`, in both views.

One check was cut for failing to fail. "Nothing of it paints under the
menu" stayed green under both faults, because "no box has any size"
already forbids anything overlapping anything. A check that cannot go
red is worse than no check, since it reads as cover.

### Clicked the tool, got no tools (2026-08-28)

The pill was gone and the basket was then unmanageable, which is a worse
fault than the one it replaced.

"Click the tool's own content to open its controls" is the editor's rule
and it is a good one -- while the content is where the tool is. A
floating basket is not: it is pinned to a corner of the viewport, and
what stands in its place in the header is a strip carrying its panel.
Clicking that strip -- the only thing where the tool used to be -- did
nothing whatsoever. The controls could be reached only by knowing to
click a 75x38 icon in the far corner of the screen, and the panel then
opened somewhere the click had not happened.

A tool's NAME opens it now. Written that way rather than as a rule about
floating baskets, because clicking a tool's own label to get its
controls is what anybody would try on any tool and there was nothing
else it could have meant. And a panel that opens outside the viewport
scrolls itself into view, since controls somebody cannot see are not
open in any sense that matters.

The reason I did not catch this is the more useful half. `basket_check.py`
asserted **its tool panel is reachable** -- `panel.getBoundingClientRect()
.height > 0` -- and that was true: the panel is a label plus a controls
box that is `display: none` until the tool is opened, so it stood 51px
tall carrying nothing anybody could use. The check measured the container
of the thing it cared about.

That is the same mistake as the check I had cut an hour earlier for
staying green under both faults, and I made it again in the same file
while writing the replacement. **Ask for the thing, not for its box.**
The check now clicks what a person would click and asks how wide the
`basket_align` select is; with the handler removed it reads
`clicking it opens the basket's own controls  FAILED  0x0`.

## Four things that read as mess, each of them a number (2026-08-28)

"Improve the overall aesthetics because it feels messy" is not a
measurable request, but every part of it turned out to be.

**The picture picker opened unstyled.** Reported as "images huge and
cut". Measured on the newsletter editor: a 332px dialog containing a
`display: block` grid of 79 tiles at their natural **1216x2009 each**,
64,805px tall, with Cancel somewhere below the horizon. The styles were
correct and complete -- they were in `inline-editor.css`, which loads
only on the live page. The comment immediately above them says the
MODAL's styles were kept out of that file "since the modal is shared
with plain admin pages that don't load inline-editor.css at all", and
the picker's were left there anyway. Extracting `image-picker.js` moved
the behaviour and not the appearance, which is the same drift the
extraction existed to end. They live in `cms-modal.css` now, which
`cms_modal.html` links itself, so they travel with the markup.

**Where a button points was a card under the message.** A label, a
full-width input and a paragraph of hint, for one field. A link is a
property of the selected block exactly as its alignment and its colour
are, and those are in the ribbon -- so it stands with them. The hint
became the field's own tooltip: a sentence of running text in a row of
controls is a large part of what made that row read as a section.

**To and Subject were the biggest thing on the screen.** Full-width
boxes with 74px labels, on a screen whose subject is the message
underneath them. Capped at 460px and shortened: 92px for the pair now.

**Send was above everything.** The order was tools / actions / To+Subject
/ message, so the button you press LAST sat above everything you do
first, live, over a message that was still empty. It is tools / To and
Subject / the message / what to do with it. Everything before the canvas
is what the message needs; everything after it is what happens to the
message -- the order of an envelope. Schedule and its time are drawn as
one control rather than a button beside a floating 240px date box, and
Delete joined that row instead of sitting alone in a card under
everything.

### An arrangement you like can be kept

`email_layouts` gains a table. A layout was already "a starting
arrangement, not a kind" -- the shipped ones are a dictionary -- so a
saved one is the same thing with its blocks written down instead of
typed out, and it joins the same dropdown. What is saved is what is on
the CANVAS, not what was last saved: somebody who has just arranged
something and likes it should not have to save the newsletter first.

It asks for a name, because a name somebody chose is one they will
recognise in that dropdown six weeks later. Saving the same name again
replaces it -- two entries with one name and no way to tell them apart
is worse than either.

And it can be removed. That is the half that keeps getting left out --
twice this week already -- so it went in with the same change rather
than after the next report. Remove wakes only on one of your own: a
shipped layout is in the code and would be back on the next boot, so a
live button there would be a button that lies. The route refuses it too,
not just the button.

### Two checker mistakes worth keeping

The removal check first counted options: "one more than before". An
earlier run that died midway had left its arrangement behind, and saving
the same name REPLACES rather than adds -- so the count was right and
the check failed, on a run where everything worked. It asserts presence
and absence by name now. **Count is almost never the claim.**

And the layout-change check drove `select_option`, which lays the blocks
out again and reloads -- three reloads deep, the check was about timing
rather than about the button. It sets the value and fires `change` for
what the button does, and posts to the route for what the route does.

### A fresh install was not checked for any of today's schema

`fresh_install_check.py` boots against an empty `DATA_DIR` twice and asks
what a first five minutes would. It knew nothing about the invoice
columns, the saved-layouts table, or the wording the four self-sending
messages ship with -- all added today.

That matters more than the usual "add a check" note, because the two
paths through a migration genuinely disagree. `_add_column` tolerates a
missing table **on purpose**: these ALTERs exist to bring an OLDER
database up to date, and on a brand new one the table may not exist yet.
Which means on a new install a misplaced `_add_column` does not fail --
it does nothing at all, silently, and the column is missing forever. That
is exactly what happened with `orders.invoice_ref`: added above the
`CREATE TABLE orders` that creates the table it alters. An existing
install was fine; a new one had no column and the first sale would have
500'd.

Proved rather than asserted. Putting the three `_add_column` calls back
above the CREATE:

    a new database has orders.invoice_ref   FAILED  ['amount_total',
      'created_at', 'currency', 'customer_id', 'id', 'line_items',
      'provider', 'provider_ref', 'status']

**Anything a migration adds gets a line in the fresh-install checker**,
not because schema drift is likely but because this particular failure is
invisible on the machine you are developing on -- your database already
has the column, from the run where the ALTER was in the right place.

Its hand-maintained total (`23 checks`) is counted now, for the same
reason `newsletter_check.py`'s was: it would have become a lie with the
first line added.

## Four pieces of feedback from using it, recorded before building (2026-08-28)

Written down first and built after, because three of the four are
re-shapings rather than fixes and the reasoning is the part worth
keeping. Where I am reading something INTO the words rather than out of
them, it says so -- those are the places to correct me.

### 1. Admin screens are set too large

"Overly large text and fields." Not one screen: the observation is
general, and it matches what the newsletter compose bar turned out to be
-- full-width boxes forty pixels tall holding an address and one line.
An admin screen is a workbench, and a workbench that shows six controls
where twelve would fit makes somebody scroll to see what they are
working on.

It wants measuring rather than taste: font sizes, control heights and
field widths across every admin screen, against what the content in them
actually needs. `screen_audit.py` already walks every screen, so the
numbers can be collected the same way the missing tooltips were.

### 2. The Newsletters screen is nine cards and should be two things

Today it is: Write a newsletter / Going out on its own / Yours / "N on
the list, M customers" / How every email opens and closes / newsletter
pages / blog posts per blog / What has gone out. Nine cards to answer
"what have I sent, and what am I sending".

What it should be:

  * **Writing one is the first thing, not a card.** The action belongs at
    the top of the screen, immediately, not inside a section that has to
    be read first.
  * **One table, not three lists.** "Yours" (drafts), "Going out on its
    own" (scheduled) and "What has gone out" (sent) are three views of
    one thing -- a newsletter at a different point in its life. One
    table: **date created, date sent, schedule name, subject, recipient
    group** (customers or everyone), and **edit, copy, delete** per row.
    Copy is new and is the obvious way to write next month's from last
    month's.
  * **Write with AI** as an option alongside writing one by hand.
  * **The list counts do not belong here.** "N on the list, M customers"
    is the Email list screen's subject, and repeating it here is the same
    number in two places, which is how two places come to disagree.
  * **A schedule is a named thing you assign, not a date you retype.**
    The "monthly newsletter" idea becomes **schedule templates**: the
    owner creates one or more named schedules ("First Monday", "Monthly,
    9am") and assigns one to a newsletter. That is why the consolidated
    table has a `schedule name` column rather than a timestamp -- the
    name is what somebody recognises, and a schedule reused across twelve
    sends should be defined once.
  * **Blog posts are CONTENT, not a section of this screen.** The "Yard
    Notes -- 2 most recent posts" card is the wrong shape: it lists a
    blog's posts on the Newsletters screen so each can be sent. Instead,
    a blog should be includable as newsletter content two ways -- as a
    **blog template** (a starting arrangement that pulls in posts) and as
    a **blog tool in the editor** (a block, like every other block). That
    is this project's own rule about features being tools rather than
    page types, applied to the newsletter editor: a capability an owner
    drops in, not a fixed section that only exists on one screen.

### 3. An intro and an exit belong to the newsletter, not to the site

"How every email opens and closes" is a pair of settings applied to every
send. It should be an **intro section and an exit section on the
newsletter template itself**, written directly into the email like every
other block -- and **past emails become the templates**, so reuse is
"start from the one I sent in June" rather than "fill in two boxes in
settings".

This follows from the saved-layout work rather than contradicting it: a
layout is a starting arrangement, and a sent newsletter is an
arrangement somebody already approved. The step is letting a SENT one be
used as a starting point, and moving the two fixed settings into blocks
so there is nothing left that is written once and applied invisibly to
everything.

Note what must survive it: the sender line and the unsubscribe link are
appended by the code and are still not fields. Those are not "how the
email opens and closes"; they are what the law requires under it.

### 4. Message wording should be one editor, and its preview should be real

Four things, and the first is a defect rather than a preference:

  * **The preview uses dummy data.** `{{site}}` reads "Your site" instead
    of the site's actual name. That was deliberate -- believable sample
    data rather than the placeholder repeated back -- and it is wrong for
    the fields this install can actually fill. The site's name, the legal
    business, the sender line: those are known, and showing them as
    invented values makes the preview a worse guide than the real thing.
    Sample data stays only where there is nothing to read from -- an
    order that has not happened yet has no total.
  * **Every message should have the same tools.** They differ today only
    because the screen grew per message.
  * **One section with a dropdown**, choosing which message to edit, into
    a reusable editor with the variables and the text tools -- the same
    editor the newsletter uses. Four cards stacked down a page is four
    copies of one screen.
  * **Preview on hover or on click**, as a popup or a real view, rather
    than a permanent second column. The side-by-side pane was built to
    answer "a sentence with `{{total}}` in it cannot be judged until it
    says 42.00 CHF"; the answer stands, but it does not have to cost half
    the width all the time.

Taken together, 3 and 4 are the same move: one editor, used by
newsletters and by the messages that send themselves, with the
differences expressed as which blocks and which variables a given
message offers.

### A blog stopped being a section and became content (2026-08-28)

Feedback item 2's other half. The Newsletters screen listed every blog
with its latest posts, so each post could be sent as an issue of its
own. That made "the blog" a part of one screen rather than something an
owner can put IN a newsletter -- and it meant a newsletter could be a
post or be written, never both.

It is a **block** now (`posts` in `BLOCK_TYPES`) and a **layout** ("From
the blog"). This project's own rule, applied to the editor: a capability
is a tool you drop in, not a fixed section that only exists on one
screen.

Three things it had to get right.

**Resolved by the caller, not inside `email_layouts`.** That module
renders an email and knows nothing about blogs or the database, which is
what keeps it callable from a template, a checker and a scheduled send
alike. `render()` takes a `posts_for` callable; the route passes one
built from `blog_service`. A caller that passes none gets an empty
block, which the canvas draws as an empty slot.

**Resolved at SEND time, and nothing about it is live.** What arrives is
what was true when it was sent. A block that re-read the blog later would
make the copy in somebody's inbox disagree with the copy in the record.
Published posts only -- a draft has no address, so including one would
put a "Read it" link into an inbox pointing at a 404, and unlike a page
an email cannot be corrected after it has gone.

**The block stores the CHOICE, not the posts.** `blog_id` and `count`,
one to ten. Storing the resolved posts would freeze them at the moment
somebody clicked, so a newsletter written on Monday and sent on Friday
would carry Monday's list.

`missing()` gained "has no blog chosen", and lost the separate
`missing_posts()` I had written ten minutes earlier -- two functions
answering "what is stopping a send" is the drift this project keeps
warning about. It also learned that a newsletter made only of posts HAS
words: somebody wrote them, in the posts, and demanding a sentence on
top would be demanding a covering note nobody wanted to write.

### The ribbon paid for it, and the bound moved with its reason

Adding a blog select and a count took the ribbon to five rows and 258px.
The toolbar was set at FORM size -- 13px controls in 190px boxes -- which
is the general "admin screens are too large" complaint in the one place
it can be measured against a target. Reset to toolbar size (12px, 150px)
it came back to four rows and 200px.

The check said three. It says four now, and the comment says why rather
than the number being quietly raised: eleven controls do not share a row
at 852px. What the bound is FOR is that the next control is not free.

### A check that passed for the wrong reason, again

"There is no separate 'What has gone out' card" passed while the card
was still in the template -- it only ever rendered `{% if history %}`,
and the install being checked had no history. True, and meaningless.

The card is genuinely gone now: those rows are in the one table, and the
only thing the card did that the table did not -- removing a single line
from the record -- the table does. The claim is asserted against the
TEMPLATE, where it cannot be true by accident.

That is the third time this week a check has passed because the thing it
was looking for could not appear. **Ask whether a check can go red
before believing it went green.**

### An opening belongs to the newsletter, not to the site (2026-08-28)

Feedback item 3. "How every email opens and closes" was two settings,
written once and applied invisibly to every send -- so the one place
they could not be read was the place they would be read from.

They are **blocks** now, with a `role` of `intro` or `exit`, written into
the newsletter where they will be read. Every shipped arrangement opens
and closes with them.

**A role, not a block type.** An opening is words and so is a sign-off;
giving them types of their own would mean two more entries in
`BLOCK_TYPES` rendering exactly like `text`, and a third the day
somebody wants a postscript. The role earns its place because the SEND
has to know something the type cannot tell it.

**Which is the part that cost nobody their words.** Removing the wrapper
outright would have silently dropped the greeting from every existing
draft -- the intro was applied at send time and is not in the blocks, so
it would simply have stopped arriving. Instead `_wrapped()` asks whether
the newsletter carries its own: one written before this has no roled
block and is still wrapped the old way; one written after is not wrapped
at all. No migration, and nothing rewritten under anybody.

**And the card did not just disappear.** A page or a post has no blocks
to hold an opening, so the setting still applies to those -- it sits
beside them now and says exactly that ("When you send a page or a post")
rather than claiming to be how every email opens. Deleting it would have
removed a capability rather than moved one.

**Past emails are templates.** A newsletter that has gone out is an
arrangement somebody approved and a reader received, which is why "start
from last month's" is how most people write this month's. Sent ones are
in the same Template dropdown, prefixed `sent:`, resolved through a
callable the caller supplies -- `email_layouts` renders an email and does
not know what a send is.

Two checker notes. Three separate checks compared a layout to a flat list
of block types and all three broke, correctly: every arrangement has two
more blocks than it did. They compare the middle now and assert the
opening and sign-off separately, which is a better statement of what the
layout IS. And `sent_composed` joined on `s.kind` where the column is
`s.target_kind` -- SQLite raised nothing, the join simply matched no rows
and the dropdown was quietly missing a section. **A join that matches
nothing looks exactly like a feature that is switched off.**
