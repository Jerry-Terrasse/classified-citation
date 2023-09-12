from nicegui import ui, app
from nicegui.elements.tabs import TabPanel
import traceback
from loguru import logger

from deal_pdf import deal, NumberedIntegrity, UnnumberedIntegrity, ResultIntegrity, PDFResult
from deal_pdf import Bibitem, Destination, Citation

from typing import cast

detail: dict = {}
last_file = ''

def update_result(result_panel: TabPanel, res: PDFResult, integrity: ResultIntegrity):
    with result_panel:
        result_panel.clear()
        
        # Summary Table
        columns = [
            {'name': 'metric', 'label': 'Metric', 'field': 'metric', 'align': 'left'},
            {'name': 'value', 'label': 'Value', 'field': 'value', 'align': 'left'},
        ]
        rows = [
            {'metric': 'Numbered', 'value': isinstance(integrity, NumberedIntegrity)},
            {'metric': 'Valid', 'value': len(res.valids)},
            {'metric': 'Total Links', 'value': len(res.cites)},
        ]
        rows.extend([
            {'metric': m, 'value': len(v) if isinstance(v, list) else v}
            for m, v in integrity.__dict__.items()
        ])
        ui.table(columns=columns, rows=rows)
        ui.separator()
        
        summary = res.summary()
        with ui.card():
            with ui.card_section():
                for idx, smy in enumerate(summary):
                    with ui.row():
                        ui.label(f'[{idx+1}]')
                        ui.markdown(f"```{smy}```")

def update_integrity(integrity_panel: TabPanel, integrity: ResultIntegrity):
    with integrity_panel:
        integrity_panel.clear()
        columns = [
            {'name': 'metric', 'label': 'Metric', 'field': 'metric', 'align': 'left'},
            {'name': 'value', 'label': 'Value', 'field': 'value', 'align': 'left'},
        ]
        rows = [
            {'metric': m, 'value': str(v)}
            for m, v in integrity.__dict__.items()
        ]
        ui.table(columns=columns, rows=rows)

def update_destination(destination_panel: TabPanel, detail: dict):
    destination_panel.clear()
    if 'dests' not in detail:
        return
    dests = cast(list[Destination], detail['dests'])
    with destination_panel:
        for idx, dest in enumerate(dests):
            with ui.row():
                ui.label(f'[{idx+1}]')
                ui.markdown(f"```{dest}```")

def update_link(link_panel: TabPanel, detail: dict):
    link_panel.clear()
    if 'links' not in detail:
        return
    links = cast(list[Citation], detail['links'])
    with link_panel:
        for idx, link in enumerate(links):
            with ui.row():
                ui.label(f'[{idx+1}]')
                ui.markdown(f"```{link}```")

def update_bibitem(bibitem_panel: TabPanel, detail: dict):
    bibitem_panel.clear()
    if 'bibs' not in detail:
        return
    bibitems = cast(list[list[Bibitem]], detail['bibs'])
    with bibitem_panel:
        for page, bibs in enumerate(bibitems):
            with ui.expansion(f"Page {page+1} ({len(bibs)} items)"):
                for idx, bib in enumerate(bibs):
                    with ui.row():
                        ui.label(f'[{idx+1}]')
                        ui.markdown(f"```{bib}```")
    
def update_contexted_link(contexted_link_panel: TabPanel, detail: dict):
    contexted_link_panel.clear()
    if 'contexted_links' not in detail:
        return
    links = cast(list[Citation], detail['contexted_links'])
    with contexted_link_panel:
        for idx, link in enumerate(links):
            with ui.row():
                ui.label(f'[{idx+1}]')
                ui.markdown(f"```{link}```")

def update_cite(cite_panel: TabPanel, detail: dict):
    cite_panel.clear()
    if 'cites' not in detail:
        return
    cites = cast(list[Citation], detail['cites'])
    with cite_panel:
        for idx, cite in enumerate(cites):
            with ui.row():
                ui.label(f'[{idx+1}]')
                ui.markdown(f"```{cite}```")

def update_bibed_cite(bibed_cite_panel: TabPanel, detail: dict):
    bibed_cite_panel.clear()
    if 'bibed_cites' not in detail:
        return
    cites = cast(list[Citation], detail['bibed_cites'])
    with bibed_cite_panel:
        for idx, cite in enumerate(cites):
            with ui.row():
                ui.label(f'[{idx+1}]')
                ui.markdown(f"```{cite}```")

def analyze():
    global detail, last_file
    # analyze_btn.style('display:none')
    # analyze_spn.style('display:inline-block')
    
    # last_file = fname.value
    # fname._props['placeholder'] = last_file
    detail = {'enabled': True}
    error_msg.content = ''
    
    logger.info(f'Analyzing {fname.value}')
    res = deal(fname.value, detail)
    integrity = res.integrity()
    
    with ui.tab_panels(tabs, value=result_tab).classes('w-full'):
        update_result(result_panel, res, integrity)
        update_integrity(integrity_panel, integrity)
        update_destination(destination_panel, detail)
        update_link(link_panel, detail)
        update_bibitem(bibitem_panel, detail)
        update_contexted_link(contexted_link_panel, detail)
        update_cite(cite_panel, detail)
        update_bibed_cite(bibed_cite_panel, detail)
        
    # analyze_btn.style('display:inline-block')
    # analyze_spn.style('display:none')

def error_handler(e):
    error_msg.content = f"""```python
{traceback.format_exc()}
```"""

ui.dark_mode(True)
app.on_exception(error_handler)

with ui.row():
    fname = ui.input(label='file', placeholder=last_file)
    analyze_btn = ui.button(text='analyze', on_click=analyze)
    analyze_spn = ui.spinner(size='lg')
    analyze_spn.style('display:none')
error_msg = ui.markdown()

with ui.tabs().classes('w-full') as tabs:
    result_tab = ui.tab('result')
    integrity_tab = ui.tab('integrity')
    destination_tab = ui.tab('destination')
    link_tab = ui.tab('link')
    bibitem_tab = ui.tab('bibitem')
    contexted_link_tab = ui.tab('contexted_link')
    cite_tab = ui.tab('cite')
    bibed_cite_tab = ui.tab('bibed_cites')
    
with ui.tab_panels(tabs, value=result_tab).classes('w-full'):
    with ui.tab_panel(result_tab) as result_panel:
        pass
    with ui.tab_panel(integrity_tab) as integrity_panel:
        pass
    with ui.tab_panel(destination_tab) as destination_panel:
        pass
    with ui.tab_panel(link_tab) as link_panel:
        pass
    with ui.tab_panel(bibitem_tab) as bibitem_panel:
        pass
    with ui.tab_panel(contexted_link_tab) as contexted_link_panel:
        pass
    with ui.tab_panel(cite_tab) as cite_panel:
        pass
    with ui.tab_panel(bibed_cite_tab) as bibed_cite_panel:
        pass
        

ui.run()