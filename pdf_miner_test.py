from pdfminer.layout import LAParams, LTTextBoxHorizontal, LTComponent, LTContainer
from pdfminer.converter import PDFPageAggregator
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter

file_path = 'pdf/2201.02915.pdf'

# 创建一个PDF资源管理器对象
resource_manager = PDFResourceManager()

# 设置参数并创建一个聚合器对象
laparams = LAParams()
device = PDFPageAggregator(resource_manager, laparams=laparams)

# 创建一个PDF页面解释器对象
interpreter = PDFPageInterpreter(resource_manager, device)

def walk(layout: LTComponent, depth: int):
    # if depth > 3:
    #     return
    prefix = ">" * (depth-1)
    print(prefix, layout.__class__.__name__)
    if hasattr(layout, "get_text"):
        print(prefix, layout.get_text()) # type: ignore
    if isinstance(layout, LTContainer):
        for child in layout:
            walk(child, depth + 1)

# 开始遍历PDF的每一页
with open(file_path, 'rb') as file:
    for page in PDFPage.get_pages(file):
        interpreter.process_page(page)
        # 获得页面的布局对象
        layout = device.get_result()
        
        walk(layout, 1)
        
        # # 遍历布局对象中的文本对象
        # for obj in layout:
        #     print(type(obj))
        #     if hasattr(obj, "get_text"):
        #         print(obj.get_text())
        #         # 对于更深入的需求，你可以在这里进一步访问和处理obj的其他属性和方法
        #     if isinstance(obj, LTTextBoxHorizontal):
        #         for line in obj:
        #             print(type(line))
        #             print(line.get_text())
        #             # 对于更深入的需求，你可以在这里进一步访问和处理line的其他属性和方法

device.close()
