import csv
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import pytest


def correction_csv(rows):
    out = StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(['调车区','修订号','提交时间','站点余缺','可行车路','原始备注'])
    writer.writerows(rows)
    return out.getvalue().encode()


# 原批次 00101 结论 4 车公里；更正把 乙>丁 公里数从 80 改为 1，最优解变为 2 车公里
CORRECTED = correction_csv([
    ['00101','2','2026-11-18T15:30:00+08:00','甲:1;乙:1;丙:-1;丁:-1','甲>丙:1:1;甲>丁:1:2;乙>丙:1:2;乙>丁:1:1','午后盘点更正'],
])


@pytest.fixture
def signed(client):
    run_id = client.post('/api/runs',json={}).json()['manifest']['run_id']
    response = client.post(f'/api/review/{run_id}',json={'version':0,'decision':'确认','note':'晨班已逐条核对'})
    assert response.status_code == 200
    return run_id


def register(client, base, payload=CORRECTED):
    return client.post(f'/api/runs/{base}/corrections',json={'data':payload.decode()})


def test_correction_keeps_base_affected_and_signoff(client,signed):
    record = register(client,signed).json()
    assert record['base_run_id'] == signed and record['run_id'] != signed
    assert record['version'] == 1 and record['replayed'] is False
    assert record['affected'] == [{'key':'00101','before':'4','after':'2','change':'CHANGED'}]
    assert record['basis']['run_id'] == signed
    assert record['basis']['manifest']['run_id'] == signed
    assert [item['decision'] for item in record['basis']['reviews']] == ['确认']
    assert record['dispatch']['use_run_id'] == record['run_id']
    assert record['dispatch']['code'] == 'USE_CORRECTION'


def test_same_correction_retry_adds_no_version(client,signed):
    first = register(client,signed).json()
    second = register(client,signed).json()
    assert second['id'] == first['id'] and second['version'] == 1
    assert second['replayed'] is True
    lineage = client.get(f'/api/runs/{signed}/corrections').json()
    assert len(lineage['as_base']) == 1
    assert lineage['as_base'][0] == {key:value for key,value in first.items() if key != 'replayed'}


def test_distinct_correction_advances_version(client,signed):
    first = register(client,signed).json()
    other = correction_csv([
        ['00104','2','2026-11-18T15:40:00+08:00','甲:2;乙:-2','乙>甲:2:1;甲>乙:2:1','再次更正'],
    ])
    second = register(client,signed,other).json()
    assert second['id'] != first['id'] and second['version'] == 2
    assert second['affected'] == [{'key':'00104','before':'0','after':'2','change':'CHANGED'}]
    assert [item['version'] for item in client.get(f'/api/runs/{signed}/corrections').json()['as_base']] == [1,2]


def test_noop_correction_keeps_base(client,signed):
    duplicate = correction_csv([
        ['00101','1','2026-11-18T09:30:00+08:00','甲:1;乙:1;丙:-1;丁:-1','甲>丙:1:1;甲>丁:1:2;乙>丙:1:2;乙>丁:1:80','重复回传'],
    ])
    record = register(client,signed,duplicate).json()
    assert record['affected'] == []
    assert record['dispatch']['code'] == 'KEEP_BASE'
    assert record['dispatch']['use_run_id'] == signed


def test_blocked_revision_removes_stale_figure(client,signed):
    broken = correction_csv([
        ['00101','2','2026-11-18T15:30:00+08:00','甲:1;乙:1;丙:-1;丁:-1','N/A','车路待补'],
    ])
    record = register(client,signed,broken).json()
    assert record['affected'] == [{'key':'00101','before':'4','after':None,'change':'REMOVED'}]
    assert record['dispatch']['code'] == 'USE_CORRECTION'


def test_base_signoff_not_overwritten(client,signed):
    record = register(client,signed).json()
    assert [item['decision'] for item in client.get(f'/api/review/{signed}').json()] == ['确认']
    assert client.get(f"/api/review/{record['run_id']}").json() == []
    export = client.get(f'/api/export/{signed}').json()
    assert export['review'][0]['decision'] == '确认'
    assert export['corrections']['as_base'][0]['id'] == record['id']


def test_correction_export_carries_lineage(client,signed):
    record = register(client,signed).json()
    lineage = client.get(f"/api/runs/{record['run_id']}/corrections").json()
    assert lineage['as_result'][0]['id'] == record['id'] and lineage['as_base'] == []
    export = client.get(f"/api/export/{record['run_id']}").json()
    linked = export['corrections']['as_result'][0]
    assert linked['base_run_id'] == signed
    assert linked['affected'][0]['key'] == '00101'
    assert linked['basis']['reviews'][0]['note'] == '晨班已逐条核对'
    assert export['review'] == []


def test_correction_defaults_to_base_book(client,signed):
    record = register(client,signed).json()
    base = client.get(f'/api/runs/{signed}').json()['manifest']
    corrected = client.get(f"/api/runs/{record['run_id']}").json()['manifest']
    assert corrected['book_sha256'] == base['book_sha256']
    assert corrected['source_sha256'] != base['source_sha256']


def test_unknown_base(client):
    response = client.post('/api/runs/not-found/corrections',json={'data':CORRECTED.decode()})
    assert (response.status_code,response.json()['code']) == (404,'RUN_UNKNOWN')


def test_invalid_correction_rejected(client,signed):
    empty = client.post(f'/api/runs/{signed}/corrections',json={})
    assert (empty.status_code,empty.json()['code']) == (422,'CORRECTION_EMPTY')
    header_only = client.post(f'/api/runs/{signed}/corrections',
                              json={'data':'调车区,修订号,提交时间,站点余缺,可行车路,原始备注\n'})
    assert header_only.json()['code'] == 'HEADER_ONLY'
    wrong_header = client.post(f'/api/runs/{signed}/corrections',json={'data':'调车区,外部记录值(车公里)\n00101,4\n'})
    assert wrong_header.json()['code'] == 'CONTRACT'
    assert client.get(f'/api/runs/{signed}/corrections').json()['as_base'] == []


def test_concurrent_retry_keeps_single_version(client):
    from app.modules.correction.service import register
    base = client.post('/api/runs',json={}).json()['manifest']['run_id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda _: register(base,CORRECTED),range(4)))
    assert {record['id'] for record in records} == {records[0]['id']}
    assert [record['version'] for record in records] == [1,1,1,1]
    assert len(client.get(f'/api/runs/{base}/corrections').json()['as_base']) == 1
