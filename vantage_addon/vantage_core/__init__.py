# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vendored snapshot of the pure `anki.vantage` scoring core.

The add-on prefers the copy that ships inside Anki (`anki.vantage`) and only
falls back to this vendored copy when it is missing, e.g. inside a packaged
build whose wheel predates the module. Keeping it here means the dashboard works
on any Anki, including a clean-machine install, once the add-on is present.
"""
