class TestRetryOfAFailedCase:
    """A case can fail for reasons unrelated to the diagnosis — a dropped connection,
    one malformed structured output. Those are independent between attempts, so a run
    that costs an hour and a dollar should not report a case unanswerable because one
    HTTP request died.
    """

    def _case(self, case_id: str = "a"):
        from eval.cases import GoldenCase

        return GoldenCase.model_validate(
            {
                "id": case_id,
                "category": "nutrient",
                "plant": {
                    "name": "Basil",
                    "species": "Ocimum basilicum",
                    "location_kind": "indoor",
                },
                "species_confidence": 0.9,
                "symptoms": {
                    "symptoms": [
                        {
                            "description": "pale lower leaves",
                            "position": "lower_leaves",
                            "severity": "monitor",
                        }
                    ],
                    "soil_condition": "moist",
                    "overall_vigor": "declining",
                },
                "ground_truth": "nitrogen-deficiency",
            }
        )

    def _run(self, case_id: str, error: str | None):
        from eval.harness import CaseRun

        return CaseRun(
            case_id=case_id,
            ground_truth="nitrogen-deficiency",
            category="nutrient",
            candidates=[] if error else ["nitrogen-deficiency"],
            reasoning="",
            contexts=[],
            questions_asked=[],
            situation="",
            usage=None,
            error=error,
        )

    def test_a_failed_case_is_attempted_again(self, monkeypatch):
        import eval.run_eval as run_eval

        attempts: list[object] = []

        def _fake_run_one(case, suffix, profile_block):
            attempts.append(suffix)
            return self._run(case.id, "APIConnectionError" if len(attempts) == 1 else None)

        monkeypatch.setattr(run_eval, "_run_one", _fake_run_one)

        runs, retried = run_eval._run_main_set([self._case()], "")

        assert len(attempts) == 2
        assert runs[0].error is None, "the second attempt's result is the one kept"
        assert retried == ["a"]

    def test_the_retry_uses_a_fresh_thread(self, monkeypatch):
        """Resuming the first attempt's checkpoint would reproduce the failure rather
        than escape it."""
        import eval.run_eval as run_eval

        suffixes: list[object] = []

        def _fake_run_one(case, suffix, profile_block):
            suffixes.append(suffix)
            return self._run(case.id, "boom" if len(suffixes) == 1 else None)

        monkeypatch.setattr(run_eval, "_run_one", _fake_run_one)
        run_eval._run_main_set([self._case()], "")

        assert suffixes[0] != suffixes[1]

    def test_a_case_that_fails_twice_stays_failed(self, monkeypatch):
        """Not retried forever, and not quietly dropped: it is counted in the
        denominator like any other failure (spec §5)."""
        import eval.run_eval as run_eval

        calls = []

        def _fake_run_one(case, suffix, profile_block):
            calls.append(suffix)
            return self._run(case.id, "still broken")

        monkeypatch.setattr(run_eval, "_run_one", _fake_run_one)

        runs, retried = run_eval._run_main_set([self._case()], "")

        assert len(calls) == 2
        assert runs[0].error == "still broken"
        assert retried == ["a"]

    def test_a_run_with_no_failures_reports_no_retries(self, monkeypatch):
        """Empty is the good answer, and it must be distinguishable from a run that
        needed rescuing — "0 failed" alone cannot say which happened."""
        import eval.run_eval as run_eval

        monkeypatch.setattr(
            run_eval, "_run_one", lambda case, suffix, profile: self._run(case.id, None)
        )

        runs, retried = run_eval._run_main_set([self._case("a"), self._case("b")], "")

        assert [r.error for r in runs] == [None, None]
        assert retried == []
