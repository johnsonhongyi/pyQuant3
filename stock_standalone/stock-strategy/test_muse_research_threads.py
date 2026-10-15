import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import muse_research_threads as research
from muse_research_threads import thread_title,research_prompt,summary_markdown


class ResearchPresentationTests(unittest.TestCase):
    def setUp(self):
        self.job={'id':'a'*32,'evidence_hash':'b'*64,'context':{'as_of':'2026-10-15T06:56:00Z','trade_date':'2026-10-15','workflow_stage':'interactive',
            'ai_runtime':{'model':'gpt-6-luna','reasoning_effort':'low'},'stocks':[{'symbol':'002343.SZ','name':'慈文传媒'},{'symbol':'603533.SH','name':'掌阅科技'}]}}
        self.result={'thread_id':'own-thread','model':'gpt-6-luna','reasoning_effort':'low','proposal':{'market_view':'市场分歧','rotation_view':'资金待确认','answer':'无已确认买点',
            'plans':[{'symbol':'002343.SZ','action':'observe','thesis':'等待VWAP确认','invalidation':'跌破VWAP','missing_data':['新资金快照']}]}}

    def test_title_contains_time_kind_code_outcome_and_unique_id(self):
        title=thread_title(self.job,self.result)
        for text in ('10-15 14:56','问答','002343','慈文传媒','观1','#aaaaaa'):self.assertIn(text,title)

    def test_preview_is_human_readable_and_evidence_is_loaded_by_tools(self):
        prompt=research_prompt(self.job)
        self.assertTrue(prompt.startswith('# Muse'))
        self.assertIn('002343.SZ 慈文传媒',prompt)
        self.assertIn('get_market_context',prompt)
        self.assertNotIn('"evidence":',prompt)

    def test_summary_has_dated_model_and_stock_conditions(self):
        summary=summary_markdown(self.job,self.result)
        for text in ('gpt-6-luna / low','002343.SZ','观察','跌破VWAP','新资金快照','执行账本'):self.assertIn(text,summary)

    def test_synthetic_and_failed_threads_are_distinct(self):
        self.job['context']['validation_scope']='synthetic_e2e'
        title=thread_title(self.job,status='失败：MODEL_TIMEOUT')
        self.assertIn('合成验收',title);self.assertIn('MODEL_TIMEOUT',title)

    def test_summary_and_index_persist_without_injecting_model_history(self):
        class App:
            project_id='test-project'
            def __init__(self):self.calls=[]
            def request(self,method,params):self.calls.append((method,params));return {}
        app=App()
        with tempfile.TemporaryDirectory() as directory,patch.object(research,'PROJECT_ROOT',Path(directory)):
            research.publish_summary(app,self.job,self.result)
            self.assertIn('002343.SZ',Path(self.result['report_path']).read_text(encoding='utf-8'))
            self.assertIn('002343', (Path(directory)/'INDEX.md').read_text(encoding='utf-8'))
        self.assertEqual([c[0] for c in app.calls],['thread/name/set'])

    def test_existing_native_project_is_reused(self):
        class App:
            def request(self,method,params):
                self.method=method
                return {'data':[{'id':'existing','name':research.PROJECT_NAME,'roots':[{'path':str(research.PROJECT_ROOT)}]}]}
        app=App()
        self.assertEqual(research.ensure_project(app),'existing')
        self.assertEqual(app.method,'project/list')


if __name__=='__main__':unittest.main()
