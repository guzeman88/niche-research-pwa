"""Process-isolated PDFium page rasterizer. No file writes or network access."""
from io import BytesIO
import sys
import pypdfium2 as pdfium


def render(path, index):
    with pdfium.PdfDocument(path) as pdf:
        page=pdf[index]
        try:
            width,height=page.get_size()
            if not width>0 or not height>0:raise ValueError('Invalid page dimensions')
            bitmap=page.render(scale=min(2,1800/max(width,height)))
            try:
                image=bitmap.to_pil()
                try:
                    output=BytesIO();image.save(output,format='PNG');return output.getvalue()
                finally:image.close()
            finally:bitmap.close()
        finally:page.close()


if __name__=='__main__':
    sys.stdout.buffer.write(render(sys.argv[1],int(sys.argv[2])))
