from __future__ import annotations

import io
import json
from dataclasses import dataclass

from PIL import Image, ImageOps

from ..config import Settings
from ..schemas import ReceiptData


class ReceiptParserError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.public_message = message
        super().__init__(message)


@dataclass
class PreparedDocument:
    images: list[bytes]
    mime_type: str


def _prepare_image(data: bytes, settings: Settings) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((settings.receipt_max_image_width, settings.receipt_max_image_height), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=90, optimize=True)
            return output.getvalue()
    except Exception as exc:
        raise ReceiptParserError("INVALID_FILE_TYPE", "Nao foi possivel preparar a imagem do comprovante.") from exc


def prepare_document(path: str, mime_type: str, settings: Settings) -> PreparedDocument:
    with open(path, "rb") as source:
        data = source.read()
    if mime_type == "application/pdf":
        try:
            import fitz

            document = fitz.open(stream=data, filetype="pdf")
            if document.page_count == 0:
                raise ReceiptParserError("INVALID_FILE_TYPE", "O PDF nao possui paginas validas.")
            if document.page_count > settings.receipt_max_pages:
                raise ReceiptParserError("MAX_PAGES_REACHED", f"O PDF possui mais de {settings.receipt_max_pages} paginas.")
            images = []
            for page in document:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                images.append(_prepare_image(pixmap.tobytes("png"), settings))
            document.close()
            return PreparedDocument(images=images, mime_type="image/jpeg")
        except ReceiptParserError:
            raise
        except Exception as exc:
            raise ReceiptParserError("INVALID_FILE_TYPE", "Nao foi possivel ler o PDF do comprovante.") from exc
    return PreparedDocument(images=[_prepare_image(data, settings)], mime_type="image/jpeg")


def parse_receipt_json(raw_content: str) -> ReceiptData:
    content = raw_content.strip()
    if content.startswith("```"):
        content = content.strip("`").strip()
        if content.lower().startswith("json"):
            content = content[4:].strip()
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict) and isinstance(parsed.get("confianca"), (int, float)):
            parsed["confianca"] = {"geral": parsed["confianca"]}
        if isinstance(parsed, dict) and isinstance(parsed.get("data"), str) and "T" in parsed["data"]:
            parsed["data"] = parsed["data"].split("T", 1)[0]
        data = ReceiptData.model_validate(parsed)
    except Exception as exc:
        raise ReceiptParserError("INVALID_MODEL_RESPONSE", "O modelo retornou dados invalidos.") from exc
    if data.tipo_documento not in {"comprovante_compra", "nota_fiscal", "comprovante_pix", "recibo", "comprovante_cartao", "fatura", "documento_desconhecido"}:
        raise ReceiptParserError("INVALID_EXTRACTED_DATA", "Tipo de documento invalido.")
    return data
