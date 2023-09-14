from pdf2image import convert_from_path
from PIL.Image import Image
import json
import io
import codecs


from utils import Rect

def cut_img(img: Image, rect: Rect, whole: Rect):
    x0, y0, x1, y1 = rect
    X0, Y0, X1, Y1 = whole
    W, H = img.size
    xr = W / (X1 - X0)
    yr = H / (Y1 - Y0)
    left, right = int((x0 - X0) * xr), int((x1 - X0) * xr)
    bottom, top = H - int((y0 - Y0) * yr), H - int((y1 - Y0) * yr)
    return img.crop((left, top, right, bottom))

def save_img(prefix: str, img: Image, rect: Rect, items: list[Rect], format="LabelMe"):
    img.save(f"{prefix}.jpg")
    # YOLOv5 PyTorch TXT
    X0, Y0, X1, Y1 = rect
    W, H = img.size
    xr = W / (X1 - X0)
    yr = H / (Y1 - Y0)
    bbox = []
    for item in items:
        x0, y0, x1, y1 = item
        left, right = (x0 - X0) * xr, (x1 - X0) * xr
        bottom, top = H - (y0 - Y0) * yr, H - (y1 - Y0) * yr
        if format == "YOLO":
            w, h = right - left, bottom - top
            cx, cy = left + w / 2, top + h / 2
            bbox.append((cx / W, cy / H, w / W, h / H))
        elif format == "LabelMe":
            bbox.append([[left, top], [right, bottom]])
    if format == "YOLO":
        with open(f"{prefix}.txt", "w") as f:
            for x, y, w, h in bbox:
                f.write(f"0 {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")
    elif format == "LabelMe":
        f = io.BytesIO()
        img.save(f, format='PNG')
        data = f.getvalue()
        encData = codecs.encode(data, 'base64').decode()
        encData = encData.replace('\n', '')
        label = {
            'version': "5.3.1",
            'flags': {},
            'imagePath': f"{prefix}.jpg",
            'imageData': encData,
            'imageHeight': H,
            'imageWidth': W,
            'shapes': [
                {
                    'label': "citation",
                    'points': item,
                    'group_id': None,
                    'shape_type': "rectangle",
                    'flags': {}
                }
                for item in bbox
            ]
        }
        json.dump(label, open(f"{prefix}.json", "w"), indent=2)
    else:
        raise NotImplementedError
    

def get_images(fname: str):
    return convert_from_path(fname)


if __name__ == '__main__':
    images = convert_from_path('pdf/Ahierarchicalmodelofreviewsforaspectbasedsentimentanalysis.pdf')

    for i in range(len(images)):
        images[i].save('page'+ str(i) +'.jpg', 'JPEG')
        print(images[i].width, images[i].height)