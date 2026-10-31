import unittest
from desktop_model_policy import latest_models,resolve_selection


class ModelPolicyTests(unittest.TestCase):
    def row(self,model,**extra):
        return {'model':model,'displayName':model,'supportedReasoningEfforts':[{'reasoningEffort':'low'},{'reasoningEffort':'high'}],'defaultReasoningEffort':'low',**extra}

    def test_latest_generation_and_family_dedup(self):
        rows=[self.row(m) for m in ['gpt-5.6-luna','gpt-5.6-terra','gpt-6-luna','gpt-6-sol','gpt-6.1-sol','gpt-6-astra']]
        self.assertEqual({m['id'] for m in latest_models(rows)},{'gpt-6-luna','gpt-6.1-sol','gpt-6-astra','gpt-5.6-terra'})

    def test_new_family_does_not_hide_other_families_or_upgrade_source(self):
        rows=[self.row('gpt-7-luna'),self.row('gpt-6.1-sol',upgrade='gpt-7-luna'),
              self.row('codex-new-family'),self.row('gpt-6-astra')]
        self.assertEqual({r['id'] for r in latest_models(rows)},
                         {'gpt-7-luna','gpt-6.1-sol','codex-new-family','gpt-6-astra'})

    def test_default_only_and_malformed_entries(self):
        rows=[None,{'model':[]},self.row('future',supportedReasoningEfforts=None),
              self.row('invalid',supportedReasoningEfforts='high'),
              self.row('levels',supportedReasoningEfforts=[None,{'reasoningEffort':'high'}])]
        self.assertEqual(latest_models(rows),[
            {'id':'future','name':'future','efforts':['low'],'default_effort':'low'},
            {'id':'levels','name':'levels','efforts':['high'],'default_effort':'high'}])

    def test_hidden_and_dated_duplicates(self):
        rows=[self.row('gpt-6-sol-2026-01-01'),self.row('gpt-6-sol-2026-02-01'),self.row('gpt-7-luna',hidden=True)]
        self.assertEqual([r['id'] for r in latest_models(rows)],['gpt-6-sol-2026-02-01'])

    def test_unavailable_model_or_effort_never_silently_falls_back(self):
        models=latest_models([self.row('gpt-6-luna')])
        self.assertEqual(resolve_selection(models,'gpt-6-luna','high'),('gpt-6-luna','high'))
        for model,effort in [('gpt-5.6-luna','low'),('gpt-6-luna','ultra')]:
            with self.assertRaises(ValueError):resolve_selection(models,model,effort)


if __name__=='__main__':unittest.main()
