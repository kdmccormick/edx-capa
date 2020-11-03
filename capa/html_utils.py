"""
Utilities for use in Mako markup.
"""


import bleach
import markupsafe
from lxml import etree
from lxml.html.clean import Cleaner

from mako.filters import decode

# Text() can be used to declare a string as plain text, as HTML() is used
# for HTML.  It simply wraps markupsafe's escape, which will HTML-escape if
# it isn't already escaped.
Text = markupsafe.escape                        # pylint: disable=invalid-name


def HTML(html):                                 # pylint: disable=invalid-name
    """
    Mark a string as already HTML, so that it won't be escaped before output.

    Use this function when formatting HTML into other strings.  It must be
    used in conjunction with ``Text()``, and both ``HTML()`` and ``Text()``
    must be closed before any calls to ``format()``::

        <%page expression_filter="h"/>
        <%!
        from django.utils.translation import ugettext as _

        from html_utils import HTML, Text
        %>
        ${Text(_("Write & send {start}email{end}")).format(
            start=HTML("<a href='mailto:{}'>").format(user.email),
            end=HTML("</a>"),
        )}

    """
    return markupsafe.Markup(html)


def strip_all_tags_but_br(string_to_strip):
    """
    Strips all tags from a string except <br/> and marks as HTML.

    Usage:
        <%page expression_filter="h"/>
        <%!
        from html_utils import strip_all_tags_but_br
        %>
        ${accomplishment_course_title | n, strip_all_tags_but_br}
    """

    if string_to_strip is None:
        string_to_strip = ""

    string_to_strip = decode.utf8(string_to_strip)
    string_to_strip = bleach.clean(string_to_strip, tags=['br'], strip=True)

    return HTML(string_to_strip)


def clean_dangerous_html(html):
    """
    Mark a string as already HTML and remove unsafe tags, so that it won't be escaped before output.
        Usage:
        <%page expression_filter="h"/>
        <%!
        from html_utils import clean_dangerous_html
        %>
        ${course_details.overview | n, clean_dangerous_html}
    """
    if not html:
        return html
    cleaner = Cleaner(style=True, inline_style=False, safe_attrs_only=False)
    html = cleaner.clean_html(html)
    return HTML(html)


def stringify_children(node):
    '''
    Return all contents of an xml tree, without the outside tags.
    e.g. if node is parse of
        "<html a="b" foo="bar">Hi <div>there <span>Bruce</span><b>!</b></div><html>"
    should return
        "Hi <div>there <span>Bruce</span><b>!</b></div>"

    fixed from
    http://stackoverflow.com/questions/4624062/get-all-text-inside-a-tag-in-lxml
    '''
    # Useful things to know:

    # node.tostring() -- generates xml for the node, including start
    #                 and end tags.  We'll use this for the children.
    # node.text -- the text after the end of a start tag to the start
    #                 of the first child
    # node.tail -- the text after the end this tag to the start of the
    #                 next element.
    parts = [node.text]
    for c in node.getchildren():
        parts.append(etree.tostring(c, with_tail=True, encoding='unicode'))

    # filter removes possible Nones in texts and tails
    return u''.join([part for part in parts if part])
