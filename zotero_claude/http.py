"""Small HTTP helpers with a fixed User-Agent and timeout."""
import urllib.request

UA_WEB = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
UA_LOCAL = "zotero-claude/1.0"            # the Zotero connector rejects browser-looking (Mozilla/...) user agents


def http(url, headers=None, data=None, method=None, timeout=60, ua=UA_WEB):
    hdr = {"User-Agent": ua}; hdr.update(headers or {})
    r = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=hdr, method=method), timeout=timeout)
    return r.status, r.headers, r.read()


def get_text(url, **kw):
    st, h, b = http(url, **kw)
    return b.decode(h.get_content_charset() or "utf-8", "replace")
