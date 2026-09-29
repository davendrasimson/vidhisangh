"""Small dependency-free PDF audit certificate generator."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader, PdfWriter


def _pdf_text(value: str) -> str:
    value = value.encode("latin-1", "replace").decode("latin-1")
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def certificate_pdf(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 16 Tf", "52 790 Td", "(Electronic Signature Certificate) Tj", "/F1 9 Tf"]
    for line in lines:
        commands.extend(["0 -22 Td", f"({_pdf_text(line[:110])}) Tj"])
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    ]
    out = BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{index} 0 obj\n".encode())
        out.write(obj)
        out.write(b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def append_certificate(source: bytes, certificate: bytes) -> bytes:
    reader = PdfReader(BytesIO(source))
    cert = PdfReader(BytesIO(certificate))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    for page in cert.pages:
        writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
