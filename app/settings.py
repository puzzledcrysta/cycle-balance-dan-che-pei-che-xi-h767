import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT / 'sample_data'
DB = Path(os.getenv('WORKBENCH_DB', str(ROOT/'state/ledger.sqlite3')))
TITLE = '单车配车席'
SLUG = 'cycle-balance'
KEY = '调车区'
FIELDS = ('站点余缺', '可行车路')
ROLE = '共享单车晨班调度员'
UNIT = '车公里'
RULE_VERSION = 'cycle-balance-1.0'
SIGNATURE = '真实调车路由'
TABS = {'intake': '晨班盘点', 'contract': '站点字段', 'quality': '调度异常', 'domain': '调度流量', 'reconcile': '运输清单', 'runs': '配车批次', 'review': '调度签核'}
