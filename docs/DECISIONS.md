# Decisions

Append-only. A reversal keeps the old reasoning and says what changed.

## 2026-09-30: tools for an outside agent first, the sidebar second

The fork was taken to let an AI agent work inside Calc. Evidence for what that should
mean came from one project built from outside LibreOffice through pyuno (a finance
workbook, about five hours of agent time, 278 shell commands):

- 33 commands only checked whether the file was open; the person was blocked or asked
  to close it five times. The file was the person's or the agent's, never both.
- 27 throwaway scripts were written only to read a value the person could see.
- 14 PDF exports were made to look at the result; every layout and chart fault was
  found that way and none by a test.

So the first thing built is a tool server an outside agent connects to, working in the
document the person has open. John ruled the sidebar chat second.

## 2026-09-30: the server runs outside LibreOffice and reaches it over a pipe

The alternative is a server inside the extension, in LibreOffice's own Python. Outside
won because the MCP SDK and its compiled dependencies install normally there, because
the tools can be tested against a private headless LibreOffice in under three seconds,
and because connecting to a running LibreOffice over a pipe had already worked first
time. `patrup/mcp-libre` (read at `edc5123`, not run) takes the inside route: its live
tools cover Writer text only, and its HTTP server listens on every interface with no
authentication. A pipe is reachable only by the same user on the same machine.

## 2026-09-30: Python 3.14, the system interpreter

pyuno exists only for the interpreter LibreOffice was built against. The practice
default is the oldest Python in bugfix support; that interpreter cannot import `uno`,
so `requires-python` is `>=3.14` and the venv includes system site packages.

## 2026-09-30: a range is rendered through PDF and poppler

LibreOffice's PNG export draws the first page of the active sheet whatever selection it
is given (26.8, measured). The PDF export honours a selection without changing the
active sheet, the selection or the modified flag, so `render` exports the range as PDF
and `pdftoppm` makes the pages. The price is poppler as a second program on PATH.

## 2026-09-30: no tool saves or closes

A write is one undo step in the open document and stays unsaved. Saving and closing are
the person's: an agent that saves can make an edit the person has not seen permanent.

## 2026-09-30: a chart change is a named undo step

Measured on LibreOffice 26.8: adding a chart through the API records an undo step with
an empty title, and changing a chart's range records one titled "Modify chart data
range". Both undo cleanly. The tools wrap each in a step with their own label and
return it, so `undo` can name exactly that step and refuse anything the person did
after it. This corrects what the first version of these tools and their README said,
that chart changes could not be undone; that claim was carried over from another
project's notes and had never been tested here.

## 2026-09-30: a date is written as a day number and given a date format

Passing `2026-09-30` to a cell as typed input stores the right day but leaves the cell
showing 46295. So `write_range` stores the day number, counted from the document's own
day zero, and applies the locale's standard date format unless the cell already has a
date format. The price: text that is exactly a valid YYYY-MM-DD date cannot be written
as text.

## 2026-09-30: filters are a thing the tools must see, learned on first real use

The first real job was filter buttons on a table of 2,500 rows. The person already
saw "filtered" rows and no header: a Standard Filter set before an import was still
hiding 2,297 rows by position and showing 205 that no longer matched. `read_range`
showed every row, hidden or not, and `render` drew a nearly blank page, so neither
said why. Finding it took raw UNO. Hence `filters` (what each table's filter shows and
how many rows it hides, the sheet's unnamed range included), `clear_filters`, and
`set_autofilter`. Filter buttons are drawn only on screen: `render` cannot show them,
so `filters` is also how to check they are there.

## 2026-09-30: the sidebar chat is parked, with a direction and no approved design

John asked for the chat panel, then parked it as issues before a design was agreed. What
was proposed and not yet accepted: a new Calc-only panel beside upstream's, leaving the
Writer panel untouched, because upstream's panel code is large, untested and tied to
editing the file and reloading it. The feature list in the issues comes from a chat
panel John built in another editor: one conversation per document that resumes the
model's session, a streamed answer, a one-line activity display, stop, and context
attached without asking. The chat would be given calc-tools and nothing else, where
upstream's panel runs the model with every permission. Two things are unknown and have
their own issues: whether an extension can make a running LibreOffice reachable, and
whether a sidebar control can show streamed text without freezing the window.
