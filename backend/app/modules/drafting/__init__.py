"""Drafting — the in-app document editor's persistent drafts.

A *draft* is an authored document (ProseMirror JSON + rendered HTML) that
autosaves as the user types, keeps named versions, exports to DOCX built from
its structure (``docx_export``), and can be filed into the document library
as a versioned ``Document``.
"""
