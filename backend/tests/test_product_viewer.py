from hashlib import sha256
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches
from services.product_viewer import read_artifact, view


def test_workbook_keeps_every_sheet_last_row_formulas_and_unknown_cached_results(tmp_path):
    path=tmp_path/'customer.xlsx'
    book=Workbook();sheet=book.active;sheet.title='Budget'
    sheet['A1']='Budget';sheet['A201']='Last customer row';sheet['B2']='=SUM(C2:C200)'
    sheet['C2']=0;sheet['C2'].number_format='$0.00'
    sheet.merge_cells('A1:C1');book.create_sheet('Instructions')['A1']='Read me'
    book.create_sheet('Hidden calculations').sheet_state='hidden';book.save(path)
    before=sha256(path.read_bytes()).hexdigest()
    result=read_artifact(path)
    assert len(result['sheets'])==3
    assert result['sheets'][0]['rows'][200][0]['value']=='Last customer row'
    formula=result['sheets'][0]['rows'][1][1]
    assert formula['formula']=='=SUM(C2:C200)' and formula['value'] is None
    assert result['sheets'][0]['rows'][1][2]['value']==0
    assert result['sheets'][2]['state']=='hidden'
    assert result['sheets'][0]['merged']==['A1:C1']
    assert sha256(path.read_bytes()).hexdigest()==before


def test_stale_package_and_non_customer_files_never_reach_file_reader(tmp_path):
    calls=[]
    engine=SimpleNamespace(job=lambda _: {'result':{'manifest':{'artifact_fingerprint':'current','render':{'customer_files':['instructions.txt']}}}},file=lambda *args:calls.append(args))
    for name,fingerprint in [('instructions.txt','old'),('../secret.txt','current'),('internal.json','current')]:
        with pytest.raises(ValueError):view(engine,'job',name,fingerprint)
    assert calls==[]
    path=tmp_path/'instructions.txt';path.write_text('Actual instructions',encoding='utf-8')
    engine.file=lambda *_:path
    result=view(engine,'job','instructions.txt','current')
    assert result['text']=='Actual instructions' and result['artifact_fingerprint']=='current'


def test_complete_slides_text_and_tables_and_archive_contents(tmp_path):
    path=tmp_path/'customer.pptx';deck=Presentation()
    for text in ['First slide','Final slide']:
        slide=deck.slides.add_slide(deck.slide_layouts[6])
        slide.shapes.add_textbox(Inches(1),Inches(1),Inches(4),Inches(1)).text=text
    table=deck.slides[-1].shapes.add_table(1,2,Inches(1),Inches(2),Inches(4),Inches(1)).table
    table.cell(0,0).text='Vendor';table.cell(0,1).text='Arrival time';deck.save(path)
    result=read_artifact(path)
    assert result['slides']==[['First slide'],['Final slide','Vendor\tArrival time']]
    package=tmp_path/'customer.zip'
    with ZipFile(package,'w') as archive:archive.writestr('instructions.txt','Actual instructions')
    assert read_artifact(package)['files']==[{'name':'instructions.txt','bytes':19}]


def test_oversized_workbooks_and_archive_expansion_fail_instead_of_truncating(tmp_path):
    path=tmp_path/'customer.xlsx';book=Workbook();book.active['A200001']='Too many rows';book.save(path)
    with pytest.raises(ValueError,match='cell limit'):read_artifact(path)
    package=tmp_path/'customer.zip'
    with ZipFile(package,'w') as archive:
        for i in range(2049):archive.writestr(str(i),'x')
    with pytest.raises(ValueError,match='size limit'):read_artifact(package)
