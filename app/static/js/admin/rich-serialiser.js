/*  Reading a written surface back as the vocabulary it was written in.

    The exact inverse of `email_layouts.rich()`: that turns a written
    vocabulary into blocks an inbox can render, this reads those blocks
    back as the same vocabulary.

        ## a heading        ### a smaller heading
        **bold**            *italic*
        [words](address)    - a bullet

    If one changes the other has to, or what was written stops reading
    back the way it was written.

    ONE file, because there are two canvases now -- the newsletter's
    blocks and the system messages -- and both are "the thing being
    written into is the thing that gets sent". A second copy of this is
    the place the two would come to disagree about what a heading is.
*/
window.cmsRichText = (function () {
  "use strict";

  function inline(node) {
    if (node.nodeType === 3) {
      return (node.nodeValue || "").replace(/\u00a0/g, " ");
    }
    if (node.nodeType !== 1) return "";
    var inner = "";
    Array.prototype.forEach.call(node.childNodes, function (kid) {
      inner += inline(kid);
    });
    var tag = node.tagName.toLowerCase();
    if (tag === "br") return "\n";
    //  Only a SPAN, never a block: a heading carries font-weight:700 as
    //  part of the email's own style, and reading that as emphasis wraps
    //  every heading in ** -- which it did.
    var styled = tag === "span" || tag === "font";
    var weight = styled && node.style ? node.style.fontWeight : "";
    var bold = tag === "strong" || tag === "b"
      || weight === "bold" || parseInt(weight, 10) >= 600;
    var italic = tag === "em" || tag === "i"
      || (styled && node.style && node.style.fontStyle === "italic");
    if (bold || italic) {
      if (!inner.trim()) return inner;
      if (bold) inner = "**" + inner + "**";
      if (italic) inner = "*" + inner + "*";
      return inner;
    }
    if (tag === "a") {
      var href = node.getAttribute("href") || "";
      return href ? "[" + inner + "](" + href + ")" : inner;
    }
    return inner;
  }

  function fromHtml(el) {
    //  One entry per BLOCK, joined by a blank line -- because a blank
    //  line is what rich() reads as the end of a block. Inside a
    //  paragraph a <br> stays a single newline, which rich() reads back
    //  as a break rather than a new paragraph.
    var out = [];
    Array.prototype.forEach.call(el.children, function (block) {
      var tag = block.tagName.toLowerCase();
      if (tag === "ul" || tag === "ol") {
        var items = [];
        Array.prototype.forEach.call(block.querySelectorAll("li"), function (li) {
          var t = inline(li).replace(/\n+/g, " ").trim();
          if (t) items.push("- " + t);
        });
        if (items.length) out.push(items.join("\n"));
        return;
      }
      var mark = (tag === "h2" || tag === "h1") ? "## "
        : ((tag === "h3" || tag === "h4") ? "### " : "");
      var body = inline(block).split("\n").map(function (line) {
        return line.trim();
      }).filter(Boolean).join("\n");
      if (!body) return;
      //  A heading is one line by definition; a break pasted into one
      //  would otherwise become a second, unmarked heading.
      out.push(mark ? mark + body.replace(/\n+/g, " ") : body);
    });
    if (!out.length) {
      //  Nothing block-level in there: a surface somebody has typed a
      //  bare line into, which is a paragraph.
      return inline(el).split("\n").map(function (l) { return l.trim(); })
        .filter(Boolean).join("\n");
    }
    return out.join("\n\n");
  }

  return { inline: inline, fromHtml: fromHtml };
}());
