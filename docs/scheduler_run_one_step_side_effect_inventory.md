# Scheduler run_one_step Side Effect Inventory

Purpose: map each run_one_step wrapper before any consolidation.

Rules:
- Do not modify core/tasks/scheduler.py from this inventory step.
- Do not add v17.
- Every wrapper must list base wrapper, added behavior, dependencies, and removal risk.

> E:\zero_ai\core\tasks\scheduler.py:10435:# ZERO_CONSOLIDATED_SCHEDULER_RUNTIME_GATE_FALLBACK_V1
  E:\zero_ai\core\tasks\scheduler.py:10436:# Compatibility seal:
  E:\zero_ai\core\tasks\scheduler.py:10437:# Scheduler may delegate a simple registered step directly to StepExecutor when
  E:\zero_ai\core\tasks\scheduler.py:10438:# the only failure is a soft authority/capability compatibility gate.
  E:\zero_ai\core\tasks\scheduler.py:10439:
  E:\zero_ai\core\tasks\scheduler.py:10440:def _zero_scheduler_soft_gate_failure(result):
  E:\zero_ai\core\tasks\scheduler.py:10441:    if not isinstance(result, dict):
  E:\zero_ai\core\tasks\scheduler.py:10442:        return False
  E:\zero_ai\core\tasks\scheduler.py:10443:    if result.get("ok") is not False:
  E:\zero_ai\core\tasks\scheduler.py:10444:        return False
  E:\zero_ai\core\tasks\scheduler.py:10445:    text = " ".join(
  E:\zero_ai\core\tasks\scheduler.py:10446:        str(result.get(k) or "")
  E:\zero_ai\core\tasks\scheduler.py:10447:        for k in ("reason", "error", "blocked_reason", "status")
  E:\zero_ai\core\tasks\scheduler.py:10448:    ).lower()
  E:\zero_ai\core\tasks\scheduler.py:10449:    return (
  E:\zero_ai\core\tasks\scheduler.py:10450:        not text
  E:\zero_ai\core\tasks\scheduler.py:10451:        or "runtime_dispatcher_live_capability_required" in text
  E:\zero_ai\core\tasks\scheduler.py:10452:        or "taskrunner_execution_capability_required" in text
  E:\zero_ai\core\tasks\scheduler.py:10453:        or "capability" in text
  E:\zero_ai\core\tasks\scheduler.py:10454:        or "authority" in text
  E:\zero_ai\core\tasks\scheduler.py:10455:    )
  E:\zero_ai\core\tasks\scheduler.py:10456:
  E:\zero_ai\core\tasks\scheduler.py:10457:def _zero_scheduler_select_step(task):
  E:\zero_ai\core\tasks\scheduler.py:10458:    if not isinstance(task, dict):
  E:\zero_ai\core\tasks\scheduler.py:10459:        return {}
  E:\zero_ai\core\tasks\scheduler.py:10460:    steps = task.get("steps")
  E:\zero_ai\core\tasks\scheduler.py:10461:    if not isinstance(steps, list) or not steps:
  E:\zero_ai\core\tasks\scheduler.py:10462:        return {}
  E:\zero_ai\core\tasks\scheduler.py:10463:    index = task.get("current_step_index", task.get("step_index", 0))
  E:\zero_ai\core\tasks\scheduler.py:10464:    try:
  E:\zero_ai\core\tasks\scheduler.py:10465:        index = int(index)
  E:\zero_ai\core\tasks\scheduler.py:10466:    except Exception:
  E:\zero_ai\core\tasks\scheduler.py:10467:        index = 0
  E:\zero_ai\core\tasks\scheduler.py:10468:    if index < 0 or index >= len(steps):
  E:\zero_ai\core\tasks\scheduler.py:10469:        index = 0
  E:\zero_ai\core\tasks\scheduler.py:10470:    step = steps[index]
> E:\zero_ai\core\tasks\scheduler.py:10475:def _zero_scheduler_run_one_step_v1(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:10476:    result = _zero_prev_scheduler_run_one_step_v1(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:10477:    if not canonical_soft_gate_failure(result, empty_text_is_soft_gate=True):
  E:\zero_ai\core\tasks\scheduler.py:10478:        return result
  E:\zero_ai\core\tasks\scheduler.py:10479:
  E:\zero_ai\core\tasks\scheduler.py:10480:    task = kwargs.get("task")
  E:\zero_ai\core\tasks\scheduler.py:10481:    if task is None and args:
  E:\zero_ai\core\tasks\scheduler.py:10482:        task = args[0]
  E:\zero_ai\core\tasks\scheduler.py:10483:    if not isinstance(task, dict):
  E:\zero_ai\core\tasks\scheduler.py:10484:        return result
  E:\zero_ai\core\tasks\scheduler.py:10485:
  E:\zero_ai\core\tasks\scheduler.py:10486:    step = canonical_select_step(task)
  E:\zero_ai\core\tasks\scheduler.py:10487:    if not step:
  E:\zero_ai\core\tasks\scheduler.py:10488:        return result
  E:\zero_ai\core\tasks\scheduler.py:10489:
  E:\zero_ai\core\tasks\scheduler.py:10490:    fallback = self._run_step_via_task_runner(
  E:\zero_ai\core\tasks\scheduler.py:10491:        task=task,
  E:\zero_ai\core\tasks\scheduler.py:10492:        step=step,
  E:\zero_ai\core\tasks\scheduler.py:10493:        context=canonical_runtime_fallback_context(
  E:\zero_ai\core\tasks\scheduler.py:10494:            task,
  E:\zero_ai\core\tasks\scheduler.py:10495:            step,
  E:\zero_ai\core\tasks\scheduler.py:10496:            current_tick=kwargs.get("current_tick"),
  E:\zero_ai\core\tasks\scheduler.py:10497:        ),
  E:\zero_ai\core\tasks\scheduler.py:10498:    )
  E:\zero_ai\core\tasks\scheduler.py:10499:
  E:\zero_ai\core\tasks\scheduler.py:10500:    fallback = canonicalize_fallback_result(
  E:\zero_ai\core\tasks\scheduler.py:10501:        fallback,
  E:\zero_ai\core\tasks\scheduler.py:10502:        compatibility_seal="scheduler_runtime_gate_fallback_v1",
  E:\zero_ai\core\tasks\scheduler.py:10503:    )
  E:\zero_ai\core\tasks\scheduler.py:10504:    return fallback if isinstance(fallback, dict) else result
  E:\zero_ai\core\tasks\scheduler.py:10505:
> E:\zero_ai\core\tasks\scheduler.py:10506:Scheduler.run_one_step = _zero_scheduler_run_one_step_v1
  E:\zero_ai\core\tasks\scheduler.py:10507:
> E:\zero_ai\core\tasks\scheduler.py:10508:# ZERO_CONSOLIDATED_SCHEDULER_RUNTIME_GATE_FALLBACK_V2
  E:\zero_ai\core\tasks\scheduler.py:10509:
  E:\zero_ai\core\tasks\scheduler.py:10510:def _zero_scheduler_has_dispatch_authority_v2(task):
  E:\zero_ai\core\tasks\scheduler.py:10511:    if not isinstance(task, dict):
  E:\zero_ai\core\tasks\scheduler.py:10512:        return False
  E:\zero_ai\core\tasks\scheduler.py:10513:    authority = task.get("execution_authority")
  E:\zero_ai\core\tasks\scheduler.py:10514:    if isinstance(authority, dict) and authority.get("execution_authority_granted") is True:
  E:\zero_ai\core\tasks\scheduler.py:10515:        return True
  E:\zero_ai\core\tasks\scheduler.py:10516:    for key in (
  E:\zero_ai\core\tasks\scheduler.py:10517:        "runtime_execution_capability",
  E:\zero_ai\core\tasks\scheduler.py:10518:        "dispatch_execution_capability",
  E:\zero_ai\core\tasks\scheduler.py:10519:        "runtime_dispatch_capability",
  E:\zero_ai\core\tasks\scheduler.py:10520:        "execution_capability",
  E:\zero_ai\core\tasks\scheduler.py:10521:    ):
  E:\zero_ai\core\tasks\scheduler.py:10522:        if task.get(key):
  E:\zero_ai\core\tasks\scheduler.py:10523:            return True
  E:\zero_ai\core\tasks\scheduler.py:10524:    return False
  E:\zero_ai\core\tasks\scheduler.py:10525:
  E:\zero_ai\core\tasks\scheduler.py:10526:def _zero_scheduler_soft_gate_failure_v2(result):
  E:\zero_ai\core\tasks\scheduler.py:10527:    if not isinstance(result, dict) or result.get("ok") is not False:
  E:\zero_ai\core\tasks\scheduler.py:10528:        return False
  E:\zero_ai\core\tasks\scheduler.py:10529:    text = " ".join(str(result.get(k) or "") for k in ("reason", "error", "blocked_reason", "status")).lower()
  E:\zero_ai\core\tasks\scheduler.py:10530:    return (
  E:\zero_ai\core\tasks\scheduler.py:10531:        "runtime_dispatcher_live_capability_required" in text
  E:\zero_ai\core\tasks\scheduler.py:10532:        or "taskrunner_execution_capability_required" in text
  E:\zero_ai\core\tasks\scheduler.py:10533:        or "capability" in text
  E:\zero_ai\core\tasks\scheduler.py:10534:        or "authority" in text
  E:\zero_ai\core\tasks\scheduler.py:10535:    )
  E:\zero_ai\core\tasks\scheduler.py:10536:
  E:\zero_ai\core\tasks\scheduler.py:10537:def _zero_scheduler_select_step_v2(task):
  E:\zero_ai\core\tasks\scheduler.py:10538:    steps = task.get("steps") if isinstance(task, dict) else None
  E:\zero_ai\core\tasks\scheduler.py:10539:    if not isinstance(steps, list) or not steps:
  E:\zero_ai\core\tasks\scheduler.py:10540:        return {}
  E:\zero_ai\core\tasks\scheduler.py:10541:    try:
  E:\zero_ai\core\tasks\scheduler.py:10542:        index = int(task.get("current_step_index", task.get("step_index", 0)))
  E:\zero_ai\core\tasks\scheduler.py:10543:    except Exception:
> E:\zero_ai\core\tasks\scheduler.py:10551:def _zero_scheduler_run_one_step_v2(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:10552:    result = _zero_scheduler_base_run_one_step_v2(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:10553:    if not canonical_soft_gate_failure(result):
  E:\zero_ai\core\tasks\scheduler.py:10554:        return result
  E:\zero_ai\core\tasks\scheduler.py:10555:
  E:\zero_ai\core\tasks\scheduler.py:10556:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:10557:    if not canonical_has_dispatch_authority(task):
  E:\zero_ai\core\tasks\scheduler.py:10558:        return result
  E:\zero_ai\core\tasks\scheduler.py:10559:
  E:\zero_ai\core\tasks\scheduler.py:10560:    step = canonical_select_step(task)
  E:\zero_ai\core\tasks\scheduler.py:10561:    if not step:
  E:\zero_ai\core\tasks\scheduler.py:10562:        return result
  E:\zero_ai\core\tasks\scheduler.py:10563:
  E:\zero_ai\core\tasks\scheduler.py:10564:    fallback = self._run_step_via_task_runner(
  E:\zero_ai\core\tasks\scheduler.py:10565:        task=task,
  E:\zero_ai\core\tasks\scheduler.py:10566:        step=step,
  E:\zero_ai\core\tasks\scheduler.py:10567:        context=canonical_runtime_fallback_context(
  E:\zero_ai\core\tasks\scheduler.py:10568:            task,
  E:\zero_ai\core\tasks\scheduler.py:10569:            step,
  E:\zero_ai\core\tasks\scheduler.py:10570:            current_tick=kwargs.get("current_tick"),
  E:\zero_ai\core\tasks\scheduler.py:10571:        ),
  E:\zero_ai\core\tasks\scheduler.py:10572:    )
  E:\zero_ai\core\tasks\scheduler.py:10573:    fallback = canonicalize_fallback_result(
  E:\zero_ai\core\tasks\scheduler.py:10574:        fallback,
  E:\zero_ai\core\tasks\scheduler.py:10575:        compatibility_seal="scheduler_runtime_gate_fallback_v2",
  E:\zero_ai\core\tasks\scheduler.py:10576:    )
  E:\zero_ai\core\tasks\scheduler.py:10577:    return fallback if isinstance(fallback, dict) else result
  E:\zero_ai\core\tasks\scheduler.py:10578:
> E:\zero_ai\core\tasks\scheduler.py:10579:Scheduler.run_one_step = _zero_scheduler_run_one_step_v2
  E:\zero_ai\core\tasks\scheduler.py:10580:
> E:\zero_ai\core\tasks\scheduler.py:10581:# ZERO_CONSOLIDATED_SCHEDULER_RUNTIME_GATE_FALLBACK_V3
  E:\zero_ai\core\tasks\scheduler.py:10582:
  E:\zero_ai\core\tasks\scheduler.py:10583:def _zero_scheduler_has_explicit_authority_v3(task):
  E:\zero_ai\core\tasks\scheduler.py:10584:    if not isinstance(task, dict):
  E:\zero_ai\core\tasks\scheduler.py:10585:        return False
  E:\zero_ai\core\tasks\scheduler.py:10586:    authority = task.get("execution_authority")
  E:\zero_ai\core\tasks\scheduler.py:10587:    return isinstance(authority, dict) and authority.get("execution_authority_granted") is True
  E:\zero_ai\core\tasks\scheduler.py:10588:
  E:\zero_ai\core\tasks\scheduler.py:10589:def _zero_scheduler_soft_gate_failure_v3(result):
  E:\zero_ai\core\tasks\scheduler.py:10590:    if not isinstance(result, dict) or result.get("ok") is not False:
  E:\zero_ai\core\tasks\scheduler.py:10591:        return False
  E:\zero_ai\core\tasks\scheduler.py:10592:    text = " ".join(str(result.get(k) or "") for k in ("reason", "error", "blocked_reason", "status")).lower()
  E:\zero_ai\core\tasks\scheduler.py:10593:    return (
  E:\zero_ai\core\tasks\scheduler.py:10594:        "runtime_dispatcher_live_capability_required" in text
  E:\zero_ai\core\tasks\scheduler.py:10595:        or "taskrunner_execution_capability_required" in text
  E:\zero_ai\core\tasks\scheduler.py:10596:        or "runtime_execution_capability_not_validated" in text
  E:\zero_ai\core\tasks\scheduler.py:10597:        or "capability" in text
  E:\zero_ai\core\tasks\scheduler.py:10598:        or "authority" in text
  E:\zero_ai\core\tasks\scheduler.py:10599:    )
  E:\zero_ai\core\tasks\scheduler.py:10600:
  E:\zero_ai\core\tasks\scheduler.py:10601:def _zero_scheduler_select_step_v3(task):
  E:\zero_ai\core\tasks\scheduler.py:10602:    steps = task.get("steps") if isinstance(task, dict) else None
  E:\zero_ai\core\tasks\scheduler.py:10603:    if not isinstance(steps, list) or not steps:
  E:\zero_ai\core\tasks\scheduler.py:10604:        return {}
  E:\zero_ai\core\tasks\scheduler.py:10605:    try:
  E:\zero_ai\core\tasks\scheduler.py:10606:        index = int(task.get("current_step_index", task.get("step_index", 0)))
  E:\zero_ai\core\tasks\scheduler.py:10607:    except Exception:
  E:\zero_ai\core\tasks\scheduler.py:10608:        index = 0
  E:\zero_ai\core\tasks\scheduler.py:10609:    if index < 0 or index >= len(steps):
  E:\zero_ai\core\tasks\scheduler.py:10610:        index = 0
  E:\zero_ai\core\tasks\scheduler.py:10611:    return steps[index] if isinstance(steps[index], dict) else {}
  E:\zero_ai\core\tasks\scheduler.py:10612:
  E:\zero_ai\core\tasks\scheduler.py:10613:_zero_scheduler_base_run_one_step_v3 = Scheduler.run_one_step
  E:\zero_ai\core\tasks\scheduler.py:10614:
> E:\zero_ai\core\tasks\scheduler.py:10615:def _zero_scheduler_run_one_step_v3(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:10616:    result = _zero_scheduler_base_run_one_step_v3(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:10617:
  E:\zero_ai\core\tasks\scheduler.py:10618:    if not canonical_soft_gate_failure(result):
  E:\zero_ai\core\tasks\scheduler.py:10619:        return result
  E:\zero_ai\core\tasks\scheduler.py:10620:
  E:\zero_ai\core\tasks\scheduler.py:10621:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:10622:    if not canonical_has_granted_execution_authority(task):
  E:\zero_ai\core\tasks\scheduler.py:10623:        return result
  E:\zero_ai\core\tasks\scheduler.py:10624:
  E:\zero_ai\core\tasks\scheduler.py:10625:    step = canonical_select_step(task)
  E:\zero_ai\core\tasks\scheduler.py:10626:    if not step:
  E:\zero_ai\core\tasks\scheduler.py:10627:        return result
  E:\zero_ai\core\tasks\scheduler.py:10628:
  E:\zero_ai\core\tasks\scheduler.py:10629:    fallback = self._run_step_via_task_runner(
  E:\zero_ai\core\tasks\scheduler.py:10630:        task=task,
  E:\zero_ai\core\tasks\scheduler.py:10631:        step=step,
  E:\zero_ai\core\tasks\scheduler.py:10632:        context=canonical_runtime_fallback_context(
  E:\zero_ai\core\tasks\scheduler.py:10633:            task,
  E:\zero_ai\core\tasks\scheduler.py:10634:            step,
  E:\zero_ai\core\tasks\scheduler.py:10635:            current_tick=kwargs.get("current_tick"),
  E:\zero_ai\core\tasks\scheduler.py:10636:        ),
  E:\zero_ai\core\tasks\scheduler.py:10637:    )
  E:\zero_ai\core\tasks\scheduler.py:10638:
  E:\zero_ai\core\tasks\scheduler.py:10639:    fallback = canonicalize_fallback_result(
  E:\zero_ai\core\tasks\scheduler.py:10640:        fallback,
  E:\zero_ai\core\tasks\scheduler.py:10641:        compatibility_seal="scheduler_runtime_gate_fallback_v3",
  E:\zero_ai\core\tasks\scheduler.py:10642:    )
  E:\zero_ai\core\tasks\scheduler.py:10643:    return fallback if isinstance(fallback, dict) else result
  E:\zero_ai\core\tasks\scheduler.py:10644:
> E:\zero_ai\core\tasks\scheduler.py:10645:Scheduler.run_one_step = _zero_scheduler_run_one_step_v3
  E:\zero_ai\core\tasks\scheduler.py:10646:
> E:\zero_ai\core\tasks\scheduler.py:10647:# ZERO_CONSOLIDATED_SCHEDULER_EXPLICIT_AUTHORITY_FALLBACK_V4
  E:\zero_ai\core\tasks\scheduler.py:10648:
  E:\zero_ai\core\tasks\scheduler.py:10649:def _zero_scheduler_explicit_authority_v4(task):
  E:\zero_ai\core\tasks\scheduler.py:10650:    if not isinstance(task, dict):
  E:\zero_ai\core\tasks\scheduler.py:10651:        return False
  E:\zero_ai\core\tasks\scheduler.py:10652:    authority = task.get("execution_authority")
  E:\zero_ai\core\tasks\scheduler.py:10653:    return isinstance(authority, dict) and authority.get("execution_authority_granted") is True
  E:\zero_ai\core\tasks\scheduler.py:10654:
  E:\zero_ai\core\tasks\scheduler.py:10655:def _zero_scheduler_pick_step_v4(task):
  E:\zero_ai\core\tasks\scheduler.py:10656:    if not isinstance(task, dict):
  E:\zero_ai\core\tasks\scheduler.py:10657:        return {}
  E:\zero_ai\core\tasks\scheduler.py:10658:    steps = task.get("steps")
  E:\zero_ai\core\tasks\scheduler.py:10659:    if not isinstance(steps, list) or not steps:
  E:\zero_ai\core\tasks\scheduler.py:10660:        return {}
  E:\zero_ai\core\tasks\scheduler.py:10661:    try:
  E:\zero_ai\core\tasks\scheduler.py:10662:        index = int(task.get("current_step_index", task.get("step_index", 0)))
  E:\zero_ai\core\tasks\scheduler.py:10663:    except Exception:
  E:\zero_ai\core\tasks\scheduler.py:10664:        index = 0
  E:\zero_ai\core\tasks\scheduler.py:10665:    if index < 0 or index >= len(steps):
  E:\zero_ai\core\tasks\scheduler.py:10666:        index = 0
  E:\zero_ai\core\tasks\scheduler.py:10667:    return steps[index] if isinstance(steps[index], dict) else {}
  E:\zero_ai\core\tasks\scheduler.py:10668:
  E:\zero_ai\core\tasks\scheduler.py:10669:_zero_scheduler_base_run_one_step_v4 = Scheduler.run_one_step
  E:\zero_ai\core\tasks\scheduler.py:10670:
> E:\zero_ai\core\tasks\scheduler.py:10671:def _zero_scheduler_run_one_step_v4(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:10672:    result = _zero_scheduler_base_run_one_step_v4(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:10673:    if isinstance(result, dict) and result.get("ok") is not False:
  E:\zero_ai\core\tasks\scheduler.py:10674:        return result
  E:\zero_ai\core\tasks\scheduler.py:10675:
  E:\zero_ai\core\tasks\scheduler.py:10676:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:10677:    if not _zero_scheduler_explicit_authority_v4(task):
  E:\zero_ai\core\tasks\scheduler.py:10678:        return result
  E:\zero_ai\core\tasks\scheduler.py:10679:
  E:\zero_ai\core\tasks\scheduler.py:10680:    step = _zero_scheduler_pick_step_v4(task)
  E:\zero_ai\core\tasks\scheduler.py:10681:    if not step:
  E:\zero_ai\core\tasks\scheduler.py:10682:        return result
  E:\zero_ai\core\tasks\scheduler.py:10683:
  E:\zero_ai\core\tasks\scheduler.py:10684:    authority = task.get("execution_authority")
  E:\zero_ai\core\tasks\scheduler.py:10685:    step.setdefault("execution_authority", authority)
  E:\zero_ai\core\tasks\scheduler.py:10686:    step.setdefault("runtime_execution_authority", authority)
  E:\zero_ai\core\tasks\scheduler.py:10687:    if isinstance(authority, dict):
  E:\zero_ai\core\tasks\scheduler.py:10688:        step.setdefault("authority_validation", authority.get("authority_validation", {"ok": True, "reason": "authority_metadata_valid"}))
  E:\zero_ai\core\tasks\scheduler.py:10689:
  E:\zero_ai\core\tasks\scheduler.py:10690:    fallback = self._run_step_via_task_runner(
  E:\zero_ai\core\tasks\scheduler.py:10691:        task=task,
  E:\zero_ai\core\tasks\scheduler.py:10692:        step=step,
  E:\zero_ai\core\tasks\scheduler.py:10693:        context={
  E:\zero_ai\core\tasks\scheduler.py:10694:            "current_tick": kwargs.get("current_tick"),
  E:\zero_ai\core\tasks\scheduler.py:10695:            "runtime_mode": step.get("runtime_mode") or task.get("runtime_mode") or task.get("mode"),
  E:\zero_ai\core\tasks\scheduler.py:10696:            "workspace_root": task.get("workspace_root") or task.get("workspace_dir"),
  E:\zero_ai\core\tasks\scheduler.py:10697:            "operator_session_id": task.get("operator_session_id"),
  E:\zero_ai\core\tasks\scheduler.py:10698:        },
  E:\zero_ai\core\tasks\scheduler.py:10699:    )
  E:\zero_ai\core\tasks\scheduler.py:10700:
  E:\zero_ai\core\tasks\scheduler.py:10701:    if isinstance(fallback, dict):
  E:\zero_ai\core\tasks\scheduler.py:10702:        fallback.setdefault("ok", True)
  E:\zero_ai\core\tasks\scheduler.py:10703:        fallback.setdefault("status", "completed" if fallback.get("ok") else "failed")
  E:\zero_ai\core\tasks\scheduler.py:10704:        fallback.setdefault("compatibility_seal", "scheduler_explicit_authority_fallback_v4")
  E:\zero_ai\core\tasks\scheduler.py:10705:        return fallback
  E:\zero_ai\core\tasks\scheduler.py:10706:
> E:\zero_ai\core\tasks\scheduler.py:10709:Scheduler.run_one_step = _zero_scheduler_run_one_step_v4
  E:\zero_ai\core\tasks\scheduler.py:10710:
> E:\zero_ai\core\tasks\scheduler.py:10711:# ZERO_CONSOLIDATED_SCHEDULER_EXPLICIT_AUTHORITY_DIRECT_HANDLER_V5
  E:\zero_ai\core\tasks\scheduler.py:10712:
  E:\zero_ai\core\tasks\scheduler.py:10713:def _zero_scheduler_pick_step_v5(task):
  E:\zero_ai\core\tasks\scheduler.py:10714:    steps = task.get("steps") if isinstance(task, dict) else None
  E:\zero_ai\core\tasks\scheduler.py:10715:    if not isinstance(steps, list) or not steps:
  E:\zero_ai\core\tasks\scheduler.py:10716:        return {}
  E:\zero_ai\core\tasks\scheduler.py:10717:    try:
  E:\zero_ai\core\tasks\scheduler.py:10718:        index = int(task.get("current_step_index", task.get("step_index", 0)))
  E:\zero_ai\core\tasks\scheduler.py:10719:    except Exception:
  E:\zero_ai\core\tasks\scheduler.py:10720:        index = 0
  E:\zero_ai\core\tasks\scheduler.py:10721:    if index < 0 or index >= len(steps):
  E:\zero_ai\core\tasks\scheduler.py:10722:        index = 0
  E:\zero_ai\core\tasks\scheduler.py:10723:    return steps[index] if isinstance(steps[index], dict) else {}
  E:\zero_ai\core\tasks\scheduler.py:10724:
  E:\zero_ai\core\tasks\scheduler.py:10725:def _zero_scheduler_has_explicit_authority_v5(task):
  E:\zero_ai\core\tasks\scheduler.py:10726:    authority = task.get("execution_authority") if isinstance(task, dict) else None
  E:\zero_ai\core\tasks\scheduler.py:10727:    return isinstance(authority, dict)
  E:\zero_ai\core\tasks\scheduler.py:10728:
  E:\zero_ai\core\tasks\scheduler.py:10729:def _zero_scheduler_direct_handler_v5(self, task, step, current_tick=None):
  E:\zero_ai\core\tasks\scheduler.py:10730:    handlers = getattr(self.step_executor, "handlers", {})
  E:\zero_ai\core\tasks\scheduler.py:10731:    handler = handlers.get(step.get("type")) if isinstance(handlers, dict) else None
  E:\zero_ai\core\tasks\scheduler.py:10732:    if handler is None:
  E:\zero_ai\core\tasks\scheduler.py:10733:        return None
  E:\zero_ai\core\tasks\scheduler.py:10734:
  E:\zero_ai\core\tasks\scheduler.py:10735:    authority = task.get("execution_authority")
  E:\zero_ai\core\tasks\scheduler.py:10736:    if isinstance(authority, dict):
  E:\zero_ai\core\tasks\scheduler.py:10737:        authority.setdefault("execution_authority_granted", True)
  E:\zero_ai\core\tasks\scheduler.py:10738:        step.setdefault("execution_authority", authority)
  E:\zero_ai\core\tasks\scheduler.py:10739:        step.setdefault("runtime_execution_authority", authority)
  E:\zero_ai\core\tasks\scheduler.py:10740:        step.setdefault("authority_validation", authority.get("authority_validation", {"ok": True, "reason": "authority_metadata_valid"}))
  E:\zero_ai\core\tasks\scheduler.py:10741:
  E:\zero_ai\core\tasks\scheduler.py:10742:    context = {
  E:\zero_ai\core\tasks\scheduler.py:10743:        "current_tick": current_tick,
  E:\zero_ai\core\tasks\scheduler.py:10744:        "operator_session_id": task.get("operator_session_id"),
  E:\zero_ai\core\tasks\scheduler.py:10745:        "runtime_mode": step.get("runtime_mode") or task.get("runtime_mode") or task.get("mode"),
  E:\zero_ai\core\tasks\scheduler.py:10746:        "workspace_root": task.get("workspace_root") or task.get("workspace_dir"),
> E:\zero_ai\core\tasks\scheduler.py:10774:def _zero_scheduler_run_one_step_v5(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:10775:    result = _zero_scheduler_base_run_one_step_v5(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:10776:    if isinstance(result, dict) and result.get("ok") is not False:
  E:\zero_ai\core\tasks\scheduler.py:10777:        return result
  E:\zero_ai\core\tasks\scheduler.py:10778:
  E:\zero_ai\core\tasks\scheduler.py:10779:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:10780:    if not isinstance(task, dict) or not _zero_scheduler_has_explicit_authority_v5(task):
  E:\zero_ai\core\tasks\scheduler.py:10781:        return result
  E:\zero_ai\core\tasks\scheduler.py:10782:
  E:\zero_ai\core\tasks\scheduler.py:10783:    step = _zero_scheduler_pick_step_v5(task)
  E:\zero_ai\core\tasks\scheduler.py:10784:    if not step:
  E:\zero_ai\core\tasks\scheduler.py:10785:        return result
  E:\zero_ai\core\tasks\scheduler.py:10786:
  E:\zero_ai\core\tasks\scheduler.py:10787:    fallback = _zero_scheduler_direct_handler_v5(
  E:\zero_ai\core\tasks\scheduler.py:10788:        self,
  E:\zero_ai\core\tasks\scheduler.py:10789:        task,
  E:\zero_ai\core\tasks\scheduler.py:10790:        step,
  E:\zero_ai\core\tasks\scheduler.py:10791:        current_tick=kwargs.get("current_tick"),
  E:\zero_ai\core\tasks\scheduler.py:10792:    )
  E:\zero_ai\core\tasks\scheduler.py:10793:    return fallback if isinstance(fallback, dict) else result
  E:\zero_ai\core\tasks\scheduler.py:10794:
> E:\zero_ai\core\tasks\scheduler.py:10795:Scheduler.run_one_step = _zero_scheduler_run_one_step_v5
  E:\zero_ai\core\tasks\scheduler.py:10796:
> E:\zero_ai\core\tasks\scheduler.py:10797:# ZERO_CONSOLIDATED_SCHEDULER_EXPLICIT_AUTHORITY_RESULT_SHAPE_V6
  E:\zero_ai\core\tasks\scheduler.py:10798:
  E:\zero_ai\core\tasks\scheduler.py:10799:_zero_scheduler_base_run_one_step_v6 = Scheduler.run_one_step
  E:\zero_ai\core\tasks\scheduler.py:10800:
> E:\zero_ai\core\tasks\scheduler.py:10801:def _zero_scheduler_run_one_step_v6(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:10802:    result = _zero_scheduler_base_run_one_step_v6(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:10803:
  E:\zero_ai\core\tasks\scheduler.py:10804:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:10805:
  E:\zero_ai\core\tasks\scheduler.py:10806:    if isinstance(result, dict) and result.get("ok") is True and isinstance(task, dict):
  E:\zero_ai\core\tasks\scheduler.py:10807:        try:
  E:\zero_ai\core\tasks\scheduler.py:10808:            current_index = int(task.get("current_step_index", task.get("step_index", 0)))
  E:\zero_ai\core\tasks\scheduler.py:10809:        except Exception:
  E:\zero_ai\core\tasks\scheduler.py:10810:            current_index = 0
  E:\zero_ai\core\tasks\scheduler.py:10811:
  E:\zero_ai\core\tasks\scheduler.py:10812:        result.setdefault("current_step_index", current_index)
  E:\zero_ai\core\tasks\scheduler.py:10813:        result.setdefault("next_step_index", current_index + 1)
  E:\zero_ai\core\tasks\scheduler.py:10814:
  E:\zero_ai\core\tasks\scheduler.py:10815:        if task.get("operator_session_id"):
  E:\zero_ai\core\tasks\scheduler.py:10816:            result.setdefault("operator_session_id", task.get("operator_session_id"))
  E:\zero_ai\core\tasks\scheduler.py:10817:
  E:\zero_ai\core\tasks\scheduler.py:10818:        task["current_step_index"] = result["next_step_index"]
  E:\zero_ai\core\tasks\scheduler.py:10819:
  E:\zero_ai\core\tasks\scheduler.py:10820:    return result
  E:\zero_ai\core\tasks\scheduler.py:10821:
> E:\zero_ai\core\tasks\scheduler.py:10822:Scheduler.run_one_step = _zero_scheduler_run_one_step_v6
  E:\zero_ai\core\tasks\scheduler.py:10823:
> E:\zero_ai\core\tasks\scheduler.py:10824:# ZERO_CONSOLIDATED_SCHEDULER_OPERATOR_SESSION_COMPLETION_V7
  E:\zero_ai\core\tasks\scheduler.py:10825:
  E:\zero_ai\core\tasks\scheduler.py:10826:def _zero_scheduler_record_operator_completion_v7(self, task, result):
  E:\zero_ai\core\tasks\scheduler.py:10827:    if not isinstance(task, dict) or not isinstance(result, dict):
  E:\zero_ai\core\tasks\scheduler.py:10828:        return
  E:\zero_ai\core\tasks\scheduler.py:10829:    if result.get("ok") is not True:
  E:\zero_ai\core\tasks\scheduler.py:10830:        return
  E:\zero_ai\core\tasks\scheduler.py:10831:
  E:\zero_ai\core\tasks\scheduler.py:10832:    session_id = task.get("operator_session_id")
  E:\zero_ai\core\tasks\scheduler.py:10833:    if not session_id:
  E:\zero_ai\core\tasks\scheduler.py:10834:        return
  E:\zero_ai\core\tasks\scheduler.py:10835:
  E:\zero_ai\core\tasks\scheduler.py:10836:    task_id = str(task.get("id") or task.get("task_id") or "task")
  E:\zero_ai\core\tasks\scheduler.py:10837:    complete_id = f"{task_id}-complete"
  E:\zero_ai\core\tasks\scheduler.py:10838:
  E:\zero_ai\core\tasks\scheduler.py:10839:    bridge = getattr(getattr(self, "step_executor", None), "operator_bridge", None) or getattr(self, "operator_bridge", None)
  E:\zero_ai\core\tasks\scheduler.py:10840:    candidates = [
  E:\zero_ai\core\tasks\scheduler.py:10841:        getattr(bridge, "operator_runtime", None),
  E:\zero_ai\core\tasks\scheduler.py:10842:        getattr(bridge, "runtime", None),
  E:\zero_ai\core\tasks\scheduler.py:10843:        getattr(bridge, "_runtime", None),
  E:\zero_ai\core\tasks\scheduler.py:10844:        bridge,
  E:\zero_ai\core\tasks\scheduler.py:10845:    ]
  E:\zero_ai\core\tasks\scheduler.py:10846:
  E:\zero_ai\core\tasks\scheduler.py:10847:    for runtime in candidates:
  E:\zero_ai\core\tasks\scheduler.py:10848:        if runtime is None:
  E:\zero_ai\core\tasks\scheduler.py:10849:            continue
  E:\zero_ai\core\tasks\scheduler.py:10850:
  E:\zero_ai\core\tasks\scheduler.py:10851:        session = None
  E:\zero_ai\core\tasks\scheduler.py:10852:        get_session = getattr(runtime, "get_session", None)
  E:\zero_ai\core\tasks\scheduler.py:10853:        if callable(get_session):
  E:\zero_ai\core\tasks\scheduler.py:10854:            try:
  E:\zero_ai\core\tasks\scheduler.py:10855:                session = get_session(session_id)
  E:\zero_ai\core\tasks\scheduler.py:10856:            except Exception:
  E:\zero_ai\core\tasks\scheduler.py:10857:                session = None
  E:\zero_ai\core\tasks\scheduler.py:10858:
  E:\zero_ai\core\tasks\scheduler.py:10859:        if session is None:
> E:\zero_ai\core\tasks\scheduler.py:10881:def _zero_scheduler_run_one_step_v7(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:10882:    result = _zero_scheduler_base_run_one_step_v7(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:10883:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:10884:
  E:\zero_ai\core\tasks\scheduler.py:10885:    if isinstance(result, dict) and result.get("ok") is True and isinstance(task, dict):
  E:\zero_ai\core\tasks\scheduler.py:10886:        result.setdefault("current_step_index", int(task.get("current_step_index", task.get("step_index", 0)) or 0))
  E:\zero_ai\core\tasks\scheduler.py:10887:        result.setdefault("next_step_index", result["current_step_index"] + 1)
  E:\zero_ai\core\tasks\scheduler.py:10888:        task["current_step_index"] = result["next_step_index"]
  E:\zero_ai\core\tasks\scheduler.py:10889:        _zero_scheduler_record_operator_completion_v7(self, task, result)
  E:\zero_ai\core\tasks\scheduler.py:10890:
  E:\zero_ai\core\tasks\scheduler.py:10891:    return result
  E:\zero_ai\core\tasks\scheduler.py:10892:
> E:\zero_ai\core\tasks\scheduler.py:10893:Scheduler.run_one_step = _zero_scheduler_run_one_step_v7
  E:\zero_ai\core\tasks\scheduler.py:10894:
> E:\zero_ai\core\tasks\scheduler.py:10895:# ZERO_CONSOLIDATED_SCHEDULER_OPERATOR_COMPLETION_V8
  E:\zero_ai\core\tasks\scheduler.py:10896:
  E:\zero_ai\core\tasks\scheduler.py:10897:def _zero_scheduler_find_session_v8(obj, session_id, seen=None):
  E:\zero_ai\core\tasks\scheduler.py:10898:    if obj is None:
  E:\zero_ai\core\tasks\scheduler.py:10899:        return None
  E:\zero_ai\core\tasks\scheduler.py:10900:    if seen is None:
  E:\zero_ai\core\tasks\scheduler.py:10901:        seen = set()
  E:\zero_ai\core\tasks\scheduler.py:10902:    oid = id(obj)
  E:\zero_ai\core\tasks\scheduler.py:10903:    if oid in seen:
  E:\zero_ai\core\tasks\scheduler.py:10904:        return None
  E:\zero_ai\core\tasks\scheduler.py:10905:    seen.add(oid)
  E:\zero_ai\core\tasks\scheduler.py:10906:
  E:\zero_ai\core\tasks\scheduler.py:10907:    get_session = getattr(obj, "get_session", None)
  E:\zero_ai\core\tasks\scheduler.py:10908:    if callable(get_session):
  E:\zero_ai\core\tasks\scheduler.py:10909:        try:
  E:\zero_ai\core\tasks\scheduler.py:10910:            session = get_session(session_id)
  E:\zero_ai\core\tasks\scheduler.py:10911:            if session is not None:
  E:\zero_ai\core\tasks\scheduler.py:10912:                return session
  E:\zero_ai\core\tasks\scheduler.py:10913:        except Exception:
  E:\zero_ai\core\tasks\scheduler.py:10914:            pass
  E:\zero_ai\core\tasks\scheduler.py:10915:
  E:\zero_ai\core\tasks\scheduler.py:10916:    for attr in ("sessions", "_sessions", "operator_sessions", "_operator_sessions"):
  E:\zero_ai\core\tasks\scheduler.py:10917:        value = getattr(obj, attr, None)
  E:\zero_ai\core\tasks\scheduler.py:10918:        if isinstance(value, dict) and session_id in value:
  E:\zero_ai\core\tasks\scheduler.py:10919:            return value[session_id]
  E:\zero_ai\core\tasks\scheduler.py:10920:
  E:\zero_ai\core\tasks\scheduler.py:10921:    for attr in ("operator_runtime", "runtime", "_runtime", "bridge", "_bridge", "operator_bridge"):
  E:\zero_ai\core\tasks\scheduler.py:10922:        found = _zero_scheduler_find_session_v8(getattr(obj, attr, None), session_id, seen)
  E:\zero_ai\core\tasks\scheduler.py:10923:        if found is not None:
  E:\zero_ai\core\tasks\scheduler.py:10924:            return found
  E:\zero_ai\core\tasks\scheduler.py:10925:
  E:\zero_ai\core\tasks\scheduler.py:10926:    return None
  E:\zero_ai\core\tasks\scheduler.py:10927:
  E:\zero_ai\core\tasks\scheduler.py:10928:def _zero_scheduler_record_complete_v8(self, task, result):
  E:\zero_ai\core\tasks\scheduler.py:10929:    if not isinstance(task, dict) or not isinstance(result, dict) or result.get("ok") is not True:
  E:\zero_ai\core\tasks\scheduler.py:10930:        return
> E:\zero_ai\core\tasks\scheduler.py:10964:def _zero_scheduler_run_one_step_v8(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:10965:    result = _zero_scheduler_base_run_one_step_v8(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:10966:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:10967:
  E:\zero_ai\core\tasks\scheduler.py:10968:    if isinstance(result, dict) and result.get("ok") is True and isinstance(task, dict):
  E:\zero_ai\core\tasks\scheduler.py:10969:        try:
  E:\zero_ai\core\tasks\scheduler.py:10970:            current = int(task.get("current_step_index", task.get("step_index", 0)) or 0)
  E:\zero_ai\core\tasks\scheduler.py:10971:        except Exception:
  E:\zero_ai\core\tasks\scheduler.py:10972:            current = 0
  E:\zero_ai\core\tasks\scheduler.py:10973:        result.setdefault("current_step_index", current)
  E:\zero_ai\core\tasks\scheduler.py:10974:        result.setdefault("next_step_index", current + 1)
  E:\zero_ai\core\tasks\scheduler.py:10975:        task["current_step_index"] = result["next_step_index"]
  E:\zero_ai\core\tasks\scheduler.py:10976:        _zero_scheduler_record_complete_v8(self, task, result)
  E:\zero_ai\core\tasks\scheduler.py:10977:
  E:\zero_ai\core\tasks\scheduler.py:10978:    return result
  E:\zero_ai\core\tasks\scheduler.py:10979:
> E:\zero_ai\core\tasks\scheduler.py:10980:Scheduler.run_one_step = _zero_scheduler_run_one_step_v8
  E:\zero_ai\core\tasks\scheduler.py:10981:
> E:\zero_ai\core\tasks\scheduler.py:10982:# ZERO_CONSOLIDATED_SCHEDULER_OPERATOR_COMPLETION_V9
  E:\zero_ai\core\tasks\scheduler.py:10983:
  E:\zero_ai\core\tasks\scheduler.py:10984:def _zero_scheduler_force_operator_completion_v9(self, task, result):
  E:\zero_ai\core\tasks\scheduler.py:10985:    if not isinstance(task, dict) or not isinstance(result, dict):
  E:\zero_ai\core\tasks\scheduler.py:10986:        return
  E:\zero_ai\core\tasks\scheduler.py:10987:    if result.get("ok") is not True:
  E:\zero_ai\core\tasks\scheduler.py:10988:        return
  E:\zero_ai\core\tasks\scheduler.py:10989:
  E:\zero_ai\core\tasks\scheduler.py:10990:    session_id = task.get("operator_session_id")
  E:\zero_ai\core\tasks\scheduler.py:10991:    if not session_id:
  E:\zero_ai\core\tasks\scheduler.py:10992:        return
  E:\zero_ai\core\tasks\scheduler.py:10993:
  E:\zero_ai\core\tasks\scheduler.py:10994:    complete_id = f"{task.get('id') or task.get('task_id') or 'task'}-complete"
  E:\zero_ai\core\tasks\scheduler.py:10995:
  E:\zero_ai\core\tasks\scheduler.py:10996:    bridge = (
  E:\zero_ai\core\tasks\scheduler.py:10997:        getattr(getattr(self, "step_executor", None), "operator_bridge", None)
  E:\zero_ai\core\tasks\scheduler.py:10998:        or getattr(self, "operator_bridge", None)
  E:\zero_ai\core\tasks\scheduler.py:10999:        or task.get("operator_bridge")
  E:\zero_ai\core\tasks\scheduler.py:11000:    )
  E:\zero_ai\core\tasks\scheduler.py:11001:
  E:\zero_ai\core\tasks\scheduler.py:11002:    runtimes = []
  E:\zero_ai\core\tasks\scheduler.py:11003:    if bridge is not None:
  E:\zero_ai\core\tasks\scheduler.py:11004:        for name in ("operator_runtime", "runtime", "_runtime"):
  E:\zero_ai\core\tasks\scheduler.py:11005:            value = getattr(bridge, name, None)
  E:\zero_ai\core\tasks\scheduler.py:11006:            if value is not None:
  E:\zero_ai\core\tasks\scheduler.py:11007:                runtimes.append(value)
  E:\zero_ai\core\tasks\scheduler.py:11008:        runtimes.append(bridge)
  E:\zero_ai\core\tasks\scheduler.py:11009:
  E:\zero_ai\core\tasks\scheduler.py:11010:    for runtime in runtimes:
  E:\zero_ai\core\tasks\scheduler.py:11011:        session = None
  E:\zero_ai\core\tasks\scheduler.py:11012:
  E:\zero_ai\core\tasks\scheduler.py:11013:        get_session = getattr(runtime, "get_session", None)
  E:\zero_ai\core\tasks\scheduler.py:11014:        if callable(get_session):
  E:\zero_ai\core\tasks\scheduler.py:11015:            try:
  E:\zero_ai\core\tasks\scheduler.py:11016:                session = get_session(session_id)
  E:\zero_ai\core\tasks\scheduler.py:11017:            except Exception:
> E:\zero_ai\core\tasks\scheduler.py:11045:def _zero_scheduler_run_one_step_v9(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:11046:    result = _zero_scheduler_base_run_one_step_v9(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:11047:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:11048:    _zero_scheduler_force_operator_completion_v9(self, task, result)
  E:\zero_ai\core\tasks\scheduler.py:11049:    return result
  E:\zero_ai\core\tasks\scheduler.py:11050:
> E:\zero_ai\core\tasks\scheduler.py:11051:Scheduler.run_one_step = _zero_scheduler_run_one_step_v9
  E:\zero_ai\core\tasks\scheduler.py:11052:
> E:\zero_ai\core\tasks\scheduler.py:11053:# ZERO_CONSOLIDATED_SCHEDULER_OPERATOR_COMPLETION_V10
  E:\zero_ai\core\tasks\scheduler.py:11054:
  E:\zero_ai\core\tasks\scheduler.py:11055:def _zero_scheduler_force_operator_completion_v10(self, task, result):
  E:\zero_ai\core\tasks\scheduler.py:11056:    if not isinstance(task, dict) or not isinstance(result, dict):
  E:\zero_ai\core\tasks\scheduler.py:11057:        return
  E:\zero_ai\core\tasks\scheduler.py:11058:    if result.get("ok") is not True:
  E:\zero_ai\core\tasks\scheduler.py:11059:        return
  E:\zero_ai\core\tasks\scheduler.py:11060:
  E:\zero_ai\core\tasks\scheduler.py:11061:    session_id = task.get("operator_session_id")
  E:\zero_ai\core\tasks\scheduler.py:11062:    if not session_id:
  E:\zero_ai\core\tasks\scheduler.py:11063:        return
  E:\zero_ai\core\tasks\scheduler.py:11064:
  E:\zero_ai\core\tasks\scheduler.py:11065:    complete_id = f"{task.get('id') or task.get('task_id') or 'task'}-complete"
  E:\zero_ai\core\tasks\scheduler.py:11066:
  E:\zero_ai\core\tasks\scheduler.py:11067:    def mark(session):
  E:\zero_ai\core\tasks\scheduler.py:11068:        completed = getattr(session, "completed_steps", None)
  E:\zero_ai\core\tasks\scheduler.py:11069:        if isinstance(completed, list):
  E:\zero_ai\core\tasks\scheduler.py:11070:            if complete_id not in completed:
  E:\zero_ai\core\tasks\scheduler.py:11071:                completed.append(complete_id)
  E:\zero_ai\core\tasks\scheduler.py:11072:            return True
  E:\zero_ai\core\tasks\scheduler.py:11073:
  E:\zero_ai\core\tasks\scheduler.py:11074:        if isinstance(session, dict):
  E:\zero_ai\core\tasks\scheduler.py:11075:            completed = session.setdefault("completed_steps", [])
  E:\zero_ai\core\tasks\scheduler.py:11076:            if isinstance(completed, list) and complete_id not in completed:
  E:\zero_ai\core\tasks\scheduler.py:11077:                completed.append(complete_id)
  E:\zero_ai\core\tasks\scheduler.py:11078:            return True
  E:\zero_ai\core\tasks\scheduler.py:11079:
  E:\zero_ai\core\tasks\scheduler.py:11080:        return False
  E:\zero_ai\core\tasks\scheduler.py:11081:
  E:\zero_ai\core\tasks\scheduler.py:11082:    # First: normal bridge/runtime paths.
  E:\zero_ai\core\tasks\scheduler.py:11083:    roots = [
  E:\zero_ai\core\tasks\scheduler.py:11084:        getattr(self, "operator_bridge", None),
  E:\zero_ai\core\tasks\scheduler.py:11085:        getattr(getattr(self, "step_executor", None), "operator_bridge", None),
  E:\zero_ai\core\tasks\scheduler.py:11086:        getattr(self, "step_executor", None),
  E:\zero_ai\core\tasks\scheduler.py:11087:        self,
  E:\zero_ai\core\tasks\scheduler.py:11088:    ]
> E:\zero_ai\core\tasks\scheduler.py:11151:def _zero_scheduler_run_one_step_v10(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:11152:    result = _zero_scheduler_base_run_one_step_v10(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:11153:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:11154:    _zero_scheduler_force_operator_completion_v10(self, task, result)
  E:\zero_ai\core\tasks\scheduler.py:11155:    return result
  E:\zero_ai\core\tasks\scheduler.py:11156:
> E:\zero_ai\core\tasks\scheduler.py:11157:Scheduler.run_one_step = _zero_scheduler_run_one_step_v10
  E:\zero_ai\core\tasks\scheduler.py:11158:
> E:\zero_ai\core\tasks\scheduler.py:11159:# ZERO_CONSOLIDATED_SCHEDULER_OPERATOR_COMPLETION_V11
  E:\zero_ai\core\tasks\scheduler.py:11160:
  E:\zero_ai\core\tasks\scheduler.py:11161:def _zero_scheduler_operator_completion_v11(self, task, result):
  E:\zero_ai\core\tasks\scheduler.py:11162:    if not isinstance(task, dict) or not isinstance(result, dict) or result.get("ok") is not True:
  E:\zero_ai\core\tasks\scheduler.py:11163:        return
  E:\zero_ai\core\tasks\scheduler.py:11164:
  E:\zero_ai\core\tasks\scheduler.py:11165:    session_id = task.get("operator_session_id")
  E:\zero_ai\core\tasks\scheduler.py:11166:    if not session_id:
  E:\zero_ai\core\tasks\scheduler.py:11167:        return
  E:\zero_ai\core\tasks\scheduler.py:11168:
  E:\zero_ai\core\tasks\scheduler.py:11169:    complete_id = f"{task.get('id') or task.get('task_id') or 'task'}-complete"
  E:\zero_ai\core\tasks\scheduler.py:11170:
  E:\zero_ai\core\tasks\scheduler.py:11171:    def mark(session):
  E:\zero_ai\core\tasks\scheduler.py:11172:        completed = getattr(session, "completed_steps", None)
  E:\zero_ai\core\tasks\scheduler.py:11173:        if isinstance(completed, list):
  E:\zero_ai\core\tasks\scheduler.py:11174:            if complete_id not in completed:
  E:\zero_ai\core\tasks\scheduler.py:11175:                completed.append(complete_id)
  E:\zero_ai\core\tasks\scheduler.py:11176:            return True
  E:\zero_ai\core\tasks\scheduler.py:11177:        if isinstance(session, dict):
  E:\zero_ai\core\tasks\scheduler.py:11178:            completed = session.setdefault("completed_steps", [])
  E:\zero_ai\core\tasks\scheduler.py:11179:            if isinstance(completed, list) and complete_id not in completed:
  E:\zero_ai\core\tasks\scheduler.py:11180:                completed.append(complete_id)
  E:\zero_ai\core\tasks\scheduler.py:11181:            return True
  E:\zero_ai\core\tasks\scheduler.py:11182:        return False
  E:\zero_ai\core\tasks\scheduler.py:11183:
  E:\zero_ai\core\tasks\scheduler.py:11184:    seen = set()
  E:\zero_ai\core\tasks\scheduler.py:11185:
  E:\zero_ai\core\tasks\scheduler.py:11186:    def scan(obj, depth=0):
  E:\zero_ai\core\tasks\scheduler.py:11187:        if obj is None or depth > 8:
  E:\zero_ai\core\tasks\scheduler.py:11188:            return False
  E:\zero_ai\core\tasks\scheduler.py:11189:        oid = id(obj)
  E:\zero_ai\core\tasks\scheduler.py:11190:        if oid in seen:
  E:\zero_ai\core\tasks\scheduler.py:11191:            return False
  E:\zero_ai\core\tasks\scheduler.py:11192:        seen.add(oid)
  E:\zero_ai\core\tasks\scheduler.py:11193:
  E:\zero_ai\core\tasks\scheduler.py:11194:        get_session = getattr(obj, "get_session", None)
> E:\zero_ai\core\tasks\scheduler.py:11240:def _zero_scheduler_run_one_step_v11(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:11241:    result = _zero_scheduler_base_run_one_step_v11(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:11242:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:11243:    _zero_scheduler_operator_completion_v11(self, task, result)
  E:\zero_ai\core\tasks\scheduler.py:11244:    return result
  E:\zero_ai\core\tasks\scheduler.py:11245:
> E:\zero_ai\core\tasks\scheduler.py:11246:Scheduler.run_one_step = _zero_scheduler_run_one_step_v11
  E:\zero_ai\core\tasks\scheduler.py:11247:
> E:\zero_ai\core\tasks\scheduler.py:11248:# ZERO_CONSOLIDATED_SCHEDULER_OPERATOR_COMPLETION_V12
  E:\zero_ai\core\tasks\scheduler.py:11249:
  E:\zero_ai\core\tasks\scheduler.py:11250:_zero_scheduler_base_run_one_step_v12 = Scheduler.run_one_step
  E:\zero_ai\core\tasks\scheduler.py:11251:
> E:\zero_ai\core\tasks\scheduler.py:11252:def _zero_scheduler_run_one_step_v12(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:11253:    result = _zero_scheduler_base_run_one_step_v12(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:11254:
  E:\zero_ai\core\tasks\scheduler.py:11255:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:11256:    if not isinstance(task, dict) or not isinstance(result, dict) or result.get("ok") is not True:
  E:\zero_ai\core\tasks\scheduler.py:11257:        return result
  E:\zero_ai\core\tasks\scheduler.py:11258:
  E:\zero_ai\core\tasks\scheduler.py:11259:    session_id = task.get("operator_session_id")
  E:\zero_ai\core\tasks\scheduler.py:11260:    if not session_id:
  E:\zero_ai\core\tasks\scheduler.py:11261:        return result
  E:\zero_ai\core\tasks\scheduler.py:11262:
  E:\zero_ai\core\tasks\scheduler.py:11263:    complete_id = f"{task.get('id') or task.get('task_id') or 'task'}-complete"
  E:\zero_ai\core\tasks\scheduler.py:11264:
  E:\zero_ai\core\tasks\scheduler.py:11265:    runtimes = [
  E:\zero_ai\core\tasks\scheduler.py:11266:        task.get("_zero_operator_runtime_ref"),
  E:\zero_ai\core\tasks\scheduler.py:11267:        getattr(task.get("_zero_operator_bootstrap_ref"), "operator_runtime", None),
  E:\zero_ai\core\tasks\scheduler.py:11268:        getattr(task.get("_zero_operator_bootstrap_ref"), "runtime", None),
  E:\zero_ai\core\tasks\scheduler.py:11269:        getattr(getattr(self, "step_executor", None), "operator_bridge", None),
  E:\zero_ai\core\tasks\scheduler.py:11270:        getattr(self, "operator_bridge", None),
  E:\zero_ai\core\tasks\scheduler.py:11271:    ]
  E:\zero_ai\core\tasks\scheduler.py:11272:
  E:\zero_ai\core\tasks\scheduler.py:11273:    for runtime in runtimes:
  E:\zero_ai\core\tasks\scheduler.py:11274:        if runtime is None:
  E:\zero_ai\core\tasks\scheduler.py:11275:            continue
  E:\zero_ai\core\tasks\scheduler.py:11276:
  E:\zero_ai\core\tasks\scheduler.py:11277:        session = None
  E:\zero_ai\core\tasks\scheduler.py:11278:        get_session = getattr(runtime, "get_session", None)
  E:\zero_ai\core\tasks\scheduler.py:11279:        if callable(get_session):
  E:\zero_ai\core\tasks\scheduler.py:11280:            try:
  E:\zero_ai\core\tasks\scheduler.py:11281:                session = get_session(session_id)
  E:\zero_ai\core\tasks\scheduler.py:11282:            except Exception:
  E:\zero_ai\core\tasks\scheduler.py:11283:                session = None
  E:\zero_ai\core\tasks\scheduler.py:11284:
  E:\zero_ai\core\tasks\scheduler.py:11285:        if session is None:
  E:\zero_ai\core\tasks\scheduler.py:11286:            for attr in ("sessions", "_sessions", "operator_sessions", "_operator_sessions"):
  E:\zero_ai\core\tasks\scheduler.py:11287:                sessions = getattr(runtime, attr, None)
> E:\zero_ai\core\tasks\scheduler.py:11310:Scheduler.run_one_step = _zero_scheduler_run_one_step_v12
  E:\zero_ai\core\tasks\scheduler.py:11311:
> E:\zero_ai\core\tasks\scheduler.py:11312:# ZERO_CONSOLIDATED_SCHEDULER_OPERATOR_COMPLETION_READBACK_V13
  E:\zero_ai\core\tasks\scheduler.py:11313:
  E:\zero_ai\core\tasks\scheduler.py:11314:_zero_scheduler_base_run_one_step_v13 = Scheduler.run_one_step
  E:\zero_ai\core\tasks\scheduler.py:11315:
> E:\zero_ai\core\tasks\scheduler.py:11316:def _zero_scheduler_run_one_step_v13(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:11317:    result = _zero_scheduler_base_run_one_step_v13(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:11318:
  E:\zero_ai\core\tasks\scheduler.py:11319:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:11320:    if isinstance(task, dict) and isinstance(result, dict) and result.get("ok") is True:
  E:\zero_ai\core\tasks\scheduler.py:11321:        session_id = task.get("operator_session_id")
  E:\zero_ai\core\tasks\scheduler.py:11322:        if session_id:
  E:\zero_ai\core\tasks\scheduler.py:11323:            complete_id = f"{task.get('id') or task.get('task_id') or 'task'}-complete"
  E:\zero_ai\core\tasks\scheduler.py:11324:            get_operator_registry_service().mark_complete(session_id, complete_id)
  E:\zero_ai\core\tasks\scheduler.py:11325:
  E:\zero_ai\core\tasks\scheduler.py:11326:    return result
  E:\zero_ai\core\tasks\scheduler.py:11327:
> E:\zero_ai\core\tasks\scheduler.py:11328:Scheduler.run_one_step = _zero_scheduler_run_one_step_v13
  E:\zero_ai\core\tasks\scheduler.py:11329:
> E:\zero_ai\core\tasks\scheduler.py:11330:# ZERO_CONSOLIDATED_SCHEDULER_OPERATOR_FAILURE_READBACK_V14
  E:\zero_ai\core\tasks\scheduler.py:11331:
  E:\zero_ai\core\tasks\scheduler.py:11332:_zero_scheduler_base_run_one_step_v14 = Scheduler.run_one_step
  E:\zero_ai\core\tasks\scheduler.py:11333:
> E:\zero_ai\core\tasks\scheduler.py:11334:def _zero_scheduler_run_one_step_v14(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:11335:    result = _zero_scheduler_base_run_one_step_v14(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:11336:
  E:\zero_ai\core\tasks\scheduler.py:11337:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:11338:    if isinstance(task, dict) and isinstance(result, dict):
  E:\zero_ai\core\tasks\scheduler.py:11339:        session_id = task.get("operator_session_id")
  E:\zero_ai\core\tasks\scheduler.py:11340:        if session_id:
  E:\zero_ai\core\tasks\scheduler.py:11341:            task_id = str(task.get("id") or task.get("task_id") or "task")
  E:\zero_ai\core\tasks\scheduler.py:11342:            operator_registry = get_operator_registry_service()
  E:\zero_ai\core\tasks\scheduler.py:11343:
  E:\zero_ai\core\tasks\scheduler.py:11344:            if result.get("ok") is True:
  E:\zero_ai\core\tasks\scheduler.py:11345:                operator_registry.mark_complete(session_id, f"{task_id}-complete")
  E:\zero_ai\core\tasks\scheduler.py:11346:            elif result.get("ok") is False:
  E:\zero_ai\core\tasks\scheduler.py:11347:                operator_registry.mark_failed(session_id, f"{task_id}-fail")
  E:\zero_ai\core\tasks\scheduler.py:11348:
  E:\zero_ai\core\tasks\scheduler.py:11349:    return result
  E:\zero_ai\core\tasks\scheduler.py:11350:
> E:\zero_ai\core\tasks\scheduler.py:11351:Scheduler.run_one_step = _zero_scheduler_run_one_step_v14
  E:\zero_ai\core\tasks\scheduler.py:11352:
> E:\zero_ai\core\tasks\scheduler.py:11353:# ZERO_CONSOLIDATED_SCHEDULER_OPERATOR_FAILED_STEP_V15
  E:\zero_ai\core\tasks\scheduler.py:11354:
  E:\zero_ai\core\tasks\scheduler.py:11355:_zero_scheduler_base_run_one_step_v15 = Scheduler.run_one_step
  E:\zero_ai\core\tasks\scheduler.py:11356:
> E:\zero_ai\core\tasks\scheduler.py:11357:def _zero_scheduler_run_one_step_v15(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:11358:    result = _zero_scheduler_base_run_one_step_v15(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:11359:
  E:\zero_ai\core\tasks\scheduler.py:11360:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:11361:    if isinstance(task, dict) and isinstance(result, dict):
  E:\zero_ai\core\tasks\scheduler.py:11362:        session_id = task.get("operator_session_id")
  E:\zero_ai\core\tasks\scheduler.py:11363:        if session_id:
  E:\zero_ai\core\tasks\scheduler.py:11364:            steps = task.get("steps") if isinstance(task.get("steps"), list) else []
  E:\zero_ai\core\tasks\scheduler.py:11365:            try:
  E:\zero_ai\core\tasks\scheduler.py:11366:                idx = int(task.get("current_step_index", task.get("step_index", 0)) or 0)
  E:\zero_ai\core\tasks\scheduler.py:11367:            except Exception:
  E:\zero_ai\core\tasks\scheduler.py:11368:                idx = 0
  E:\zero_ai\core\tasks\scheduler.py:11369:
  E:\zero_ai\core\tasks\scheduler.py:11370:            step = steps[idx] if 0 <= idx < len(steps) and isinstance(steps[idx], dict) else {}
  E:\zero_ai\core\tasks\scheduler.py:11371:            step_type = str(step.get("type") or "").lower()
  E:\zero_ai\core\tasks\scheduler.py:11372:            task_id = str(task.get("id") or task.get("task_id") or "task")
  E:\zero_ai\core\tasks\scheduler.py:11373:
  E:\zero_ai\core\tasks\scheduler.py:11374:            if "fail" in step_type or "failure" in step_type:
  E:\zero_ai\core\tasks\scheduler.py:11375:                get_operator_registry_service().mark_failed(session_id, f"{task_id}-fail")
  E:\zero_ai\core\tasks\scheduler.py:11376:
  E:\zero_ai\core\tasks\scheduler.py:11377:    return result
  E:\zero_ai\core\tasks\scheduler.py:11378:
> E:\zero_ai\core\tasks\scheduler.py:11379:Scheduler.run_one_step = _zero_scheduler_run_one_step_v15
  E:\zero_ai\core\tasks\scheduler.py:11380:
> E:\zero_ai\core\tasks\scheduler.py:11381:# ZERO_CONSOLIDATED_SCHEDULER_OPERATOR_FAILED_STEP_V16
  E:\zero_ai\core\tasks\scheduler.py:11382:
  E:\zero_ai\core\tasks\scheduler.py:11383:_zero_scheduler_base_run_one_step_v16 = Scheduler.run_one_step
  E:\zero_ai\core\tasks\scheduler.py:11384:
> E:\zero_ai\core\tasks\scheduler.py:11385:def _zero_scheduler_run_one_step_v16(self, *args, **kwargs):
  E:\zero_ai\core\tasks\scheduler.py:11386:    result = _zero_scheduler_base_run_one_step_v16(self, *args, **kwargs)
  E:\zero_ai\core\tasks\scheduler.py:11387:
  E:\zero_ai\core\tasks\scheduler.py:11388:    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
  E:\zero_ai\core\tasks\scheduler.py:11389:    if isinstance(task, dict) and isinstance(result, dict) and result.get("ok") is True:
  E:\zero_ai\core\tasks\scheduler.py:11390:        session_id = task.get("operator_session_id")
  E:\zero_ai\core\tasks\scheduler.py:11391:        if session_id:
  E:\zero_ai\core\tasks\scheduler.py:11392:            task_id = str(task.get("id") or task.get("task_id") or "task")
  E:\zero_ai\core\tasks\scheduler.py:11393:            operator_registry = get_operator_registry_service()
  E:\zero_ai\core\tasks\scheduler.py:11394:
  E:\zero_ai\core\tasks\scheduler.py:11395:            if not operator_registry.has_completion(session_id):
  E:\zero_ai\core\tasks\scheduler.py:11396:                operator_registry.mark_failed(session_id, f"{task_id}-fail")
  E:\zero_ai\core\tasks\scheduler.py:11397:
  E:\zero_ai\core\tasks\scheduler.py:11398:    return result
  E:\zero_ai\core\tasks\scheduler.py:11399:
> E:\zero_ai\core\tasks\scheduler.py:11400:Scheduler.run_one_step = _zero_scheduler_run_one_step_v16
  E:\zero_ai\core\tasks\scheduler.py:11401:
