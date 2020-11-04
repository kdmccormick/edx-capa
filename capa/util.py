"""
Utility functions for capa.
"""


import logging
import math
import re
from cmath import isinf, isnan
from decimal import Decimal

import bleach
import markupsafe
import six
from calc import evaluator
from lxml import etree
from lxml.html.clean import Cleaner
from mako.filters import decode

# -----------------------------------------------------------------------------
#
# Utility functions used in CAPA responsetypes
default_tolerance = "0.001%"
log = logging.getLogger(__name__)


def compare_with_tolerance(
    student_complex,
    instructor_complex,
    tolerance=default_tolerance,
    relative_tolerance=False,
):
    """
    Compare student_complex to instructor_complex with maximum tolerance tolerance.

     - student_complex    :  student result (float complex number)
     - instructor_complex    :  instructor result (float complex number)
     - tolerance   :  float, or string (representing a float or a percentage)
     - relative_tolerance: bool, to explicitly use passed tolerance as relative

     Note: when a tolerance is a percentage (i.e. '10%'), it will compute that
     percentage of the instructor result and yield a number.

     If relative_tolerance is set to False, it will use that value and the
     instructor result to define the bounds of valid student result:
     instructor_complex = 10, tolerance = '10%' will give [9.0, 11.0].

     If relative_tolerance is set to True, it will use that value and both
     instructor result and student result to define the bounds of valid student
     result:
     instructor_complex = 10, student_complex = 20, tolerance = '10%' will give
     [8.0, 12.0].
     This is typically used internally to compare float, with a
     default_tolerance = '0.001%'.

     Default tolerance of 1e-3% is added to compare two floats for
     near-equality (to handle machine representation errors).
     Default tolerance is relative, as the acceptable difference between two
     floats depends on the magnitude of the floats.
     (http://randomascii.wordpress.com/2012/02/25/comparing-floating-point-numbers-2012-edition/)
     Examples:
        In [183]: 0.000016 - 1.6*10**-5
        Out[183]: -3.3881317890172014e-21
        In [212]: 1.9e24 - 1.9*10**24
        Out[212]: 268435456.0
    """
    if isinstance(tolerance, str):
        if tolerance == default_tolerance:
            relative_tolerance = True
        if tolerance.endswith("%"):
            tolerance = evaluator(dict(), dict(), tolerance[:-1]) * 0.01
            if not relative_tolerance:
                tolerance = tolerance * abs(instructor_complex)
        else:
            tolerance = evaluator(dict(), dict(), tolerance)

    if relative_tolerance:
        tolerance = tolerance * max(abs(student_complex), abs(instructor_complex))

    if isinf(student_complex) or isinf(instructor_complex):
        # If an input is infinite, we can end up with `abs(student_complex-instructor_complex)` and
        # `tolerance` both equal to infinity. Then, below we would have
        # `inf <= inf` which is a fail. Instead, compare directly.
        return student_complex == instructor_complex

    # because student_complex and instructor_complex are not necessarily
    # complex here, we enforce it here:
    student_complex = complex(student_complex)
    instructor_complex = complex(instructor_complex)

    # if both the instructor and student input are real,
    # compare them as Decimals to avoid rounding errors
    if not (instructor_complex.imag or student_complex.imag):
        # if either of these are not a number, short circuit and return False
        if isnan(instructor_complex.real) or isnan(student_complex.real):
            return False
        student_decimal = Decimal(str(student_complex.real))
        instructor_decimal = Decimal(str(instructor_complex.real))
        tolerance_decimal = Decimal(str(tolerance))
        return abs(student_decimal - instructor_decimal) <= tolerance_decimal

    else:
        # v1 and v2 are, in general, complex numbers:
        # there are some notes about backward compatibility issue: see responsetypes.get_staff_ans()).
        return abs(student_complex - instructor_complex) <= tolerance


def contextualize_text(text, context):  # private
    """
    Takes a string with variables. E.g. $a+$b.
    Does a substitution of those variables from the context
    """

    def convert_to_str(value):
        """The method tries to convert unicode/non-ascii values into string"""
        try:
            return str(value)
        except UnicodeEncodeError:
            return value.encode("utf8", errors="ignore")

    if not text:
        return text

    for key in sorted(context, key=len, reverse=True):
        # TODO (vshnayder): This whole replacement thing is a big hack
        # right now--context contains not just the vars defined in the
        # program, but also e.g. a reference to the numpy module.
        # Should be a separate dict of variables that should be
        # replaced.
        context_key = "$" + key
        if context_key in (
            text.decode("utf-8") if six.PY3 and isinstance(text, bytes) else text
        ):
            text = convert_to_str(text)
            context_value = convert_to_str(context[key])
            text = text.replace(context_key, context_value)

    return text


def convert_files_to_filenames(answers):
    """
    Check for File objects in the dict of submitted answers,
        convert File objects to their filename (string)
    """
    new_answers = dict()
    for answer_id in answers.keys():
        answer = answers[answer_id]
        # Files are stored as a list, even if one file
        if is_list_of_files(answer):
            new_answers[answer_id] = [f.name for f in answer]
        else:
            new_answers[answer_id] = answers[answer_id]
    return new_answers


def is_list_of_files(files):
    return isinstance(files, list) and all(is_file(f) for f in files)


def is_file(file_to_test):
    """
    Duck typing to check if 'file_to_test' is a File object
    """
    return all(hasattr(file_to_test, method) for method in ["read", "name"])


def find_with_default(node, path, default):
    """
    Look for a child of node using , and return its text if found.
    Otherwise returns default.

    Arguments:
       node: lxml node
       path: xpath search expression
       default: value to return if nothing found

    Returns:
       node.find(path).text if the find succeeds, default otherwise.

    """
    v = node.find(path)
    if v is not None:
        return v.text
    else:
        return default


def sanitize_html(html_code):
    """
    Sanitize html_code for safe embed on LMS pages.

    Used to sanitize XQueue responses from Matlab.
    """
    attributes = bleach.ALLOWED_ATTRIBUTES.copy()
    attributes.update(
        {
            "*": ["class", "style", "id"],
            "audio": ["controls", "autobuffer", "autoplay", "src"],
            "img": ["src", "width", "height", "class"],
        }
    )
    output = bleach.clean(
        html_code,
        protocols=bleach.ALLOWED_PROTOCOLS + ["data"],
        tags=bleach.ALLOWED_TAGS + ["div", "p", "audio", "pre", "img", "span"],
        styles=["white-space"],
        attributes=attributes,
    )
    return output


def get_inner_html_from_xpath(xpath_node):
    """
    Returns inner html as string from xpath node.

    """
    # returns string from xpath node
    html = etree.tostring(xpath_node).strip().decode("utf-8")
    # strips outer tag from html string
    # xss-lint: disable=python-interpolate-html
    inner_html = re.sub(
        "(?ms)<%s[^>]*>(.*)</%s>" % (xpath_node.tag, xpath_node.tag), "\\1", html
    )
    return inner_html.strip()


def remove_markup(html):
    """
    Return html with markup stripped and text HTML-escaped.

    >>> bleach.clean("<b>Rock & Roll</b>", tags=[], strip=True)
    u'Rock &amp; Roll'
    >>> bleach.clean("<b>Rock &amp; Roll</b>", tags=[], strip=True)
    u'Rock &amp; Roll'
    """
    return HTML(bleach.clean(html, tags=[], strip=True))


def round_away_from_zero(number, digits=0):
    """
    Round numbers using the 'away from zero' strategy as opposed to the
    'Banker's rounding strategy.'  The strategy refers to how we round when
    a number is half way between two numbers.  eg. 0.5, 1.5, etc. In python 2
    positive numbers in this category would be rounded up and negative numbers
    would be rounded down. ie. away from zero.  In python 3 numbers round
    towards even.  So 0.5 would round to 0 but 1.5 would round to 2.

    See here for more on floating point rounding strategies:
    https://en.wikipedia.org/wiki/IEEE_754#Rounding_rules

    We want to continue to round away from zero so that student grades remain
    consistent and don't suddenly change.
    """
    p = 10.0 ** digits

    if number >= 0:
        return float(math.floor((number * p) + 0.5)) / p
    else:
        return float(math.ceil((number * p) - 0.5)) / p


# -*- coding: utf-8 -*-


def stringify_children(node):
    """
    Return all contents of an xml tree, without the outside tags.
    e.g. if node is parse of
        "<html a="b" foo="bar">Hi <div>there <span>Bruce</span><b>!</b></div><html>"
    should return
        "Hi <div>there <span>Bruce</span><b>!</b></div>"

    fixed from
    http://stackoverflow.com/questions/4624062/get-all-text-inside-a-tag-in-lxml
    """
    # Useful things to know:

    # node.tostring() -- generates xml for the node, including start
    #                 and end tags.  We'll use this for the children.
    # node.text -- the text after the end of a start tag to the start
    #                 of the first child
    # node.tail -- the text after the end this tag to the start of the
    #                 next element.
    parts = [node.text]
    for c in node.getchildren():
        parts.append(etree.tostring(c, with_tail=True, encoding="unicode"))

    # filter removes possible Nones in texts and tails
    return u"".join([part for part in parts if part])


# Text() can be used to declare a string as plain text, as HTML() is used
# for HTML.  It simply wraps markupsafe's escape, which will HTML-escape if
# it isn't already escaped.
Text = markupsafe.escape  # pylint: disable=invalid-name


def HTML(html):  # pylint: disable=invalid-name
    """
    Mark a string as already HTML, so that it won't be escaped before output.

    Use this function when formatting HTML into other strings.  It must be
    used in conjunction with ``Text()``, and both ``HTML()`` and ``Text()``
    must be closed before any calls to ``format()``::

        <%page expression_filter="h"/>
        <%!
        from django.utils.translation import ugettext as _

        from capa.util import HTML, Text
        %>
        ${Text(_("Write & send {start}email{end}")).format(
            start=HTML("<a href='mailto:{}'>").format(user.email),
            end=HTML("</a>"),
        )}

    """
    return markupsafe.Markup(html)
