# Test source inventory

Source-derived declarations, not a test execution or pass report. Parameterized tests may generate many more cases than the declared function count. Browser dependencies may be optional or skipped in a given environment.

Read the behavioral acceptance matrix in PROJECT_SPECIFICATION.md before treating any suite as sufficient for deployment.

Inventory totals: 314 Python test-function declarations and 46 named JavaScript test declarations. These are not collected-case or passing-case totals.

## tests/test_additional_opening_filters.py

11 test function declarations.

- `test_history_excludes_old_outlier_today_future_and_uses_trading_sessions` — line 34.
- `test_two_day_color_and_strict_boundary_matrix` — line 51.
- `test_live_preview_confirmed_and_backtest_agree` — line 62.
- `test_missing_or_invalid_cache_never_passes` — line 90.
- `test_two_day_missing_open_is_unresolved` — line 110.
- `test_legacy_cache_refresh_reuses_confirmed_candle` — line 117.
- `test_settings_recheck_confirmed_results_without_network_and_persist` — line 137.
- `test_short_optional_history_allows_shared_preparation_but_blocks_green_backtest` — line 152.
- `test_redwala_never_requires_optional_history_live_backtest_or_settings_save` — line 167.
- `test_retest_obeys_new_filters` — line 193.
- `test_old_settings_default_to_off` — line 207.

## tests/test_algo.py

63 test function declarations.

- `test_ladder_reversal_and_target_locks_day` — line 26.
- `test_pyramids_original_reference_and_reversal_resets` — line 44.
- `test_capital_sizing_for_each_add` — line 63.
- `test_trailing_ratchets_and_fixed_stop_does_not` — line 72.
- `test_max_loss_and_reversal_limit_and_cutoff` — line 83.
- `test_partial_entry_uses_completed_average_for_original_stop` — line 91.
- `test_settings_reject_invalid_risk` — line 103.
- `test_replay_adverse_first_and_gap_price` — line 107.
- `test_websocket_transient_stop_latches_before_recovery` — line 176.
- `test_ltp_triggers_not_spread_and_depth_prices_paper_fill` — line 190.
- `test_tick_trailing_highwater_and_target_survive_busy_worker` — line 204.
- `test_tick_target_latched_and_no_network_on_receiver` — line 216.
- `test_missing_depth_retains_reverse_signal_until_available` — line 231.
- `test_triggered_live_flatten_needs_no_depth` — line 245.
- `test_stale_tick_cannot_trigger_and_no_per_tick_broker_reads` — line 258.
- `test_risk_during_partial_fill_cancels_then_flattens_even_if_fill_finishes` — line 274.
- `test_exit_supersedes_add_if_tick_arrives_during_preflight` — line 292.
- `test_market_feed_snapshot_separate_from_order_socket` — line 309.
- `test_event_worker_uses_ticks_with_scanner_stopped_and_no_quote_poll` — line 318.
- `test_partial_reverse_monitors_new_side_without_interrupting_old_side_close` — line 345.
- `test_market_observation_does_not_erase_worker_day_lock_or_sizing` — line 371.
- `test_square_off_reached_during_preflight_never_opens_exposure` — line 384.
- `test_credentials_changed_during_preflight_blocks_submission` — line 403.
- `test_fallback_fetches_only_missing_data_off_the_order_worker` — line 412.
- `test_paper_entry_and_reversal_use_no_broker_orders` — line 446.
- `test_live_ack_is_not_fill_and_partial_trade_is_deduplicated` — line 455.
- `test_uncertain_submission_is_reconciled_without_resend` — line 471.
- `test_intent_is_durable_before_submit` — line 480.
- `test_partial_cancel_flattens_only_actual_exposure` — line 492.
- `test_pending_order_cancel_waits_for_final_state` — line 501.
- `test_rejected_exit_pauses_without_automatic_order_loop` — line 510.
- `test_preflight_blocks_unsafe_submission` — line 523.
- `test_manual_live_exit_does_not_require_quote_or_socket` — line 534.
- `test_reconciliation_disagreement_blocks_next_action` — line 542.
- `test_restart_pauses_and_journal_has_exclusive_owner` — line 551.
- `test_duplicate_start_and_day_lock` — line 563.
- `test_only_confirmed_current_day_setups_can_start` — line 571.
- `test_snapshot_settings_do_not_mutate_active_session` — line 581.
- `test_backtest_qualifies_without_future_bars_and_forces_paper` — line 590.
- `test_position_match_ignores_other_products` — line 613.
- `test_algo_backtest_obeys_setup_price_filters` — line 626.
- `test_exit_click_during_submission_prevents_new_entry` — line 672.
- `test_trade_identity_mismatch_blocks_application` — line 687.
- `test_cancel_retry_is_bounded_and_never_resubmits` — line 695.
- `test_broker_quotes_use_shared_throttle_and_reject_stale_depth` — line 705.
- `test_broker_submission_uses_market_intraday_and_correlation` — line 723.
- `test_algo_api_contract_and_no_network` — line 734.
- `test_order_socket_authenticates_and_only_wakes_reconciliation` — line 755.
- `test_replay_maximum_loss_executes_at_threshold` — line 775.
- `test_selected_first_direction_controls_entry_and_reversal` — line 789.
- `test_first_direction_backwards_compatible_and_validated` — line 810.
- `test_opening_extreme_is_not_revisited_after_close_reversal` — line 817.
- `test_backtest_ignores_stop_touch_that_recovers_before_close` — line 841.
- `test_max_loss_trigger_tolerates_float_roundoff_at_exact_threshold` — line 851.
- `test_arcil_long_close_entry_does_not_use_earlier_low` — line 863.
- `test_trailing_reversal_is_confirmed_once_at_close` — line 882.
- `test_backtest_does_not_reverse_at_end_of_data_or_square_off` — line 894.
- `test_live_reversal_still_submits_immediately_when_stop_is_hit` — line 904.
- `test_entry_candle_ignores_extremes_regardless_of_colour` — line 916.
- `test_entry_close_can_exit_at_close_not_intraminute_threshold` — line 928.
- `test_following_candle_resumes_ohlc_stop_checks` — line 941.
- `test_entry_high_low_do_not_move_trailing_watermark` — line 953.
- `test_entry_candle_pyramid_uses_close_once` — line 964.

## tests/test_algo_browser.py

1 test function declarations.

- `test_browser_selected_stock_paper_exit_backtest` — line 18.

## tests/test_algo_feed.py

8 test function declarations.

- `test_full_feed_parses_ltp_and_best_depth_including_joined_packets` — line 32.
- `test_older_stale_unknown_invalid_packets_rejected` — line 41.
- `test_ltp_still_delivered_without_valid_depth` — line 55.
- `test_older_rest_response_cannot_replace_newer_websocket_tick` — line 63.
- `test_full_subscription_and_dynamic_unsubscribe_without_scanner` — line 74.
- `test_subscription_batches_respect_100_instrument_limit` — line 96.
- `test_disconnect_packet_is_not_a_price_and_marks_reason` — line 113.
- `test_reconnect_clears_depth_and_resubscribes_without_exposing_token` — line 120.

## tests/test_api.py

11 test function declarations.

- `test_config_and_state_endpoints_respond` — line 24.
- `test_symbols_endpoint_rejects_empty_list` — line 37.
- `test_saved_credentials_survive_refresh_and_blank_save_without_exposing_token` — line 44.
- `test_dashboard_versions_assets_and_does_not_cache_html` — line 62.
- `test_dashboard_serves_current_versioned_filter_script` — line 80.
- `test_volume_settings_endpoint_persists_and_returns_current_settings` — line 90.
- `test_repair_endpoint_checks_opening_candidates` — line 115.
- `test_cache_volume_endpoint` — line 137.
- `test_backtest_endpoint` — line 147.
- `test_removed_premarket_setup_cannot_start_or_backtest` — line 171.
- `test_afternoon_feature_removed_without_removing_scanner_or_algo` — line 189.

## tests/test_audit_regressions.py

3 test function declarations.

- `test_open_cross_refetches_incomplete_raw_cache_after_toggle` — line 16.
- `test_stop_endpoint_is_responsive_when_sdk_disconnect_blocks` — line 36.
- `test_sdk_async_feed_close_is_bounded_and_aborts_stuck_transport` — line 70.

## tests/test_cache_pipeline.py

14 test function declarations.

- `test_legacy_migration_separates_settings_and_updates_only_one_stock` — line 24.
- `test_failed_migration_is_retryable_and_does_not_overwrite_new_data` — line 44.
- `test_concurrent_stores_keep_other_symbols_and_newer_snapshot` — line 58.
- `test_266_stocks_publish_before_batch_flush_and_do_not_rewrite_config` — line 79.
- `test_daily_rollover_fetches_delta_and_backtest_cannot_use_future` — line 102.
- `test_malformed_daily_cache_recovers` — line 125.
- `test_opening_samples_roll_forward_and_keep_previous_close_context` — line 134.
- `test_missing_opening_recovery_logs_timestamps_and_uses_wide_only_on_retry` — line 155.
- `test_confirmation_skips_busy_preparation_without_duplicate_requests` — line 178.
- `test_confirmation_keeps_retrying_after_six_passes` — line 200.
- `test_scheduler_reserves_every_fourth_waiting_slot_for_background` — line 220.
- `test_empty_or_stale_daily_delta_requires_full_recheck` — line 248.
- `test_old_future_or_malformed_opening_cache_cannot_supply_samples` — line 266.
- `test_empty_opening_delta_refetches_full_window` — line 279.

## tests/test_circuit_band_browser.py

1 test function declarations.

- `test_verified_band_filter_from_quote_to_browser_and_reload` — line 13.

## tests/test_circuit_band_filter.py

9 test function declarations.

- `test_verify_both_sides_not_ltp_distance` — line 12.
- `test_ltp_changes_do_not_change_verified_band_or_fetch_again` — line 26.
- `test_incomplete_asymmetric_invalid_or_unrecognised_band_is_unknown` — line 44.
- `test_rounding_and_low_price_safeguard` — line 49.
- `test_reference_prefers_same_quote_change_and_dated_history_only` — line 56.
- `test_undated_previous_close_cannot_verify_band` — line 69.
- `test_stale_previous_day_and_future_quote_cannot_pass` — line 76.
- `test_known_fno_is_dynamic_and_quote_failure_clears_previous_verification` — line 87.
- `test_new_qualifier_gets_quote_without_refetching_old_qualifier` — line 107.

## tests/test_circuits.py

14 test function declarations.

- `test_user_example_and_distances_update_from_websocket_without_quote_calls` — line 43.
- `test_installed_sdk_quote_envelope_is_unwrapped` — line 60.
- `test_at_circuit_is_zero_not_missing` — line 82.
- `test_invalid_limits_do_not_remove_candidate` — line 90.
- `test_partial_limit_can_display_independently` — line 100.
- `test_bad_ltp_or_outside_band_does_not_give_misleading_distance` — line 108.
- `test_expired_or_previous_date_limits_are_unavailable` — line 117.
- `test_rate_limit_failure_and_later_recovery_preserve_badges` — line 126.
- `test_batches_only_current_qualified_stocks_including_redwala` — line 142.
- `test_quote_does_not_overwrite_a_newer_websocket_tick` — line 153.
- `test_removed_symbol_is_not_written_back_by_inflight_quote` — line 166.
- `test_quote_batches_respect_1000_instrument_limit` — line 179.
- `test_polling_worker_stops_on_event` — line 187.
- `test_ohlc_and_circuit_quotes_share_throttle` — line 203.

## tests/test_daily_filter.py

10 test function declarations.

- `test_daily_boundaries` — line 36.
- `test_daily_ignores_target_and_future_and_sorts_returned_dates` — line 46.
- `test_invalid_daily_history_is_not_a_pass` — line 59.
- `test_live_and_backtest_share_all_qualification_rules` — line 103.
- `test_sdk_cache_restart_repair_backtest_and_api_contract` — line 179.
- `test_daily_auth_failure_clears_existing_badges_and_stops_batch` — line 232.
- `test_stale_daily_check_is_refetched_before_evaluation` — line 248.
- `test_live_refresh_checks_first_at_916_and_retries_without_second` — line 262.
- `test_incomplete_first_candle_does_not_qualify` — line 301.
- `test_first_only_914_label_remains_supported` — line 317.

## tests/test_dashboard_integration.py

3 test function declarations.

- `test_opening_gap_badge_uses_backend_prices_without_requiring_high_break` — line 12.
- `test_scanner_controls_cache_filters_and_backtest_in_browser` — line 74.
- `test_dashboard_volume_display_filter_in_browser` — line 181.

## tests/test_dhan_contracts.py

4 test function declarations.

- `test_sdk_quote_nested_envelope_and_ltp_without_depth` — line 20.
- `test_sdk_quote_inner_failure_is_not_empty_success` — line 40.
- `test_sdk_order_body_and_documented_empty_cancel_response` — line 49.
- `test_broker_identity_mismatch_never_applies_fills` — line 73.

## tests/test_first_candle.py

5 test function declarations.

- `test_strict_crosses_match_live_and_backtest_without_second_candle` — line 19.
- `test_previous_levels_use_last_completed_session_and_ignore_future` — line 39.
- `test_invalid_levels_cannot_create_cross_badges` — line 50.
- `test_daily_and_minute_requests_share_023_second_spacing` — line 59.
- `test_pending_refresh_skips_confirmed_stock_and_has_no_per_stock_sleep` — line 80.

## tests/test_integration_workflows.py

13 test function declarations.

- `test_api_cache_settings_repair_backtest_and_restart` — line 35.
- `test_redwala_missing_daily_data_retries_and_restores_low_badge` — line 57.
- `test_dh905_daily_failure_is_explicit_partial_redwala_result` — line 74.
- `test_backtest_auth_failure_preserves_redwala_but_stops_remaining_requests` — line 97.
- `test_retest_does_not_reuse_previous_session_volume_cache` — line 108.
- `test_backtest_cannot_qualify_unfinished_first_candle` — line 123.
- `test_malformed_broker_candles_never_break_api_or_qualify` — line 133.
- `test_failed_feed_start_does_not_leave_scanner_running` — line 148.
- `test_stopping_during_history_request_cannot_publish_late_candidate` — line 168.
- `test_browser_real_api_settings_cache_backtest_and_badges` — line 209.
- `test_backtest_api_enforces_open_gap_and_returns_first_close` — line 274.
- `test_manual_symbol_resolution_failure_preserves_saved_and_running_list` — line 297.
- `test_backtest_request_settings_win_over_another_tabs_saved_filters` — line 311.

## tests/test_launcher.py

2 test function declarations.

- `test_launcher_checks_server_identity_without_crashing` — line 15.
- `test_launcher_unresponsive_server_is_not_ready` — line 22.

## tests/test_member_access.py

7 test function declarations.

- `test_signup_mfa_approval_dashboard_and_suspension` — line 69.
- `test_all_admin_endpoints_deny_member_and_anonymous` — line 88.
- `test_admin_csrf_settings_and_member_status` — line 105.
- `test_totp_replay_attempt_limits_encryption_and_reset` — line 122.
- `test_expiration_and_lost_key_fail_closed` — line 142.
- `test_rate_limit_and_transport` — line 157.
- `test_shared_filters_and_exact_priority` — line 174.

## tests/test_members_browser.py

1 test function declarations.

- `test_signup_approval_shared_dashboard_and_suspension` — line 21.

## tests/test_open_cross.py

7 test function declarations.

- `test_five_trading_sessions_ignore_calendar_gaps_older_outlier_today_and_future` — line 29.
- `test_toggle_strict_open_boundary_matches_live_preview_confirmed_and_backtest` — line 47.
- `test_changing_toggle_rechecks_existing_confirmed_results_without_network` — line 73.
- `test_legacy_cache_upgrades_and_reuses_confirmed_first_candle` — line 87.
- `test_insufficient_history_is_unresolved_when_on_and_does_not_block_when_off` — line 110.
- `test_redwala_unaffected_by_toggle_even_without_five_closes` — line 127.
- `test_toggle_persistence_default_and_old_settings_migration` — line 150.

## tests/test_opening_patterns.py

12 test function declarations.

- `test_retest_sequence` — line 48.
- `test_equality_and_missing_minutes_do_not_confirm` — line 55.
- `test_live_and_backtest_retest_after_fifth_candle_without_open_high` — line 66.
- `test_retest_uses_saved_filters_and_settings_reapply_history` — line 92.
- `test_retest_open_cross_does_not_change_redwala` — line 101.
- `test_retest_daily_filter_failure_cannot_qualify` — line 114.
- `test_live_high_break_uses_later_ltp_is_strict_and_latches` — line 122.
- `test_high_break_in_backtest_and_not_for_red_first` — line 140.
- `test_worker_only_fetches_eligible_red_and_ignores_forming_bar` — line 153.
- `test_worker_stop_during_request_cannot_publish` — line 182.
- `test_today_backtest_does_not_confirm_forming_breaking_candle` — line 195.
- `test_worker_fills_missing_open_cross_history_for_retest_without_gating_redwala` — line 206.

## tests/test_preopen.py

12 test function declarations.

- `test_script_direction_and_universe_rules` — line 37.
- `test_limits_inclusive_top_n_after_membership_price_fallback_and_stable_sort` — line 44.
- `test_bom_multiline_headers_numeric_formats_duplicates_and_missing_values` — line 54.
- `test_bad_csv_never_becomes_a_stock_list` — line 69.
- `test_invalid_settings` — line 78.
- `test_preview_is_read_only_apply_replaces_universe_and_survives_reload` — line 83.
- `test_resolution_failure_preserves_existing_list` — line 106.
- `test_csv_import_browser_workflow` — line 117.
- `test_detailed_nse_value_in_rupees_normalized_before_filtering` — line 197.
- `test_crore_header_takes_precedence_and_is_not_converted_twice` — line 206.
- `test_explicit_rupee_units` — line 215.
- `test_raw_nse_turnover_preview_apply_and_reload_in_browser` — line 222.

## tests/test_redwala_turnover.py

8 test function declarations.

- `test_redwala_only_turnover_even_without_minute_samples` — line 17.
- `test_turnover_equality_fails_and_saving_turnover_rechecks_without_network` — line 38.
- `test_daily_and_minute_fetch_errors_do_not_hide_redwala` — line 50.
- `test_low_badges_strict_thresholds_and_backtest_parity` — line 63.
- `test_ticks_break_lows_without_cumulative_volume_and_latch_after_rebound` — line 82.
- `test_missing_previous_low_suppresses_only_pdl_badge` — line 102.
- `test_daily_failed_red_live_preview_not_rejected_by_minute_volume` — line 112.
- `test_bulk_cache_failure_keeps_only_current_confirmed_redwala` — line 124.

## tests/test_resistance.py

17 test function declarations.

- `test_short_listing_history_selects_confirmed_peak_and_counts_trading_days` — line 50.
- `test_age_lookback_pullback` — line 66.
- `test_missing_or_invalid_history_is_pending_not_no_level` — line 71.
- `test_confirmation_no_future_peaks_equal_highs_and_retired_levels` — line 84.
- `test_nearest_overhead_peak_and_strict_buffer` — line 96.
- `test_settings_validation` — line 109.
- `test_daily_history_excludes_today_and_persists_raw_ohlc` — line 113.
- `test_live_later_cross_without_fetch_and_badges_scope` — line 122.
- `test_backtest_later_green_close_and_first_two_open_cross` — line 146.
- `test_replay_ignores_wicks_red_closes_and_equality` — line 165.
- `test_redwala_and_retest_unaffected_by_missing_resistance` — line 175.
- `test_old_cache_refresh_once_and_no_peak_is_not_retried` — line 188.
- `test_daily_fetch_extends_one_request_and_reuses_cached_selection` — line 204.
- `test_missing_resistance_remains_pending_even_with_volume_cache` — line 219.
- `test_live_resistance_uses_fresh_quote_price_without_websocket` — line 233.
- `test_algo_replay_cannot_enter_before_resistance_confirmation` — line 247.
- `test_browser_settings_persistence_badges_and_backtest` — line 268.

## tests/test_scanner.py

26 test function declarations.

- `test_parse_symbols_deduplicates_and_accepts_commas` — line 24.
- `test_completed_candle_turnover_uses_candle_close` — line 28.
- `test_snapshot_sorts_by_percent_change_then_turnover` — line 40.
- `test_instrument_resolver_selects_nse_equity` — line 56.
- `test_cache_previous_closes_updates_state_and_store` — line 74.
- `test_cache_previous_closes_uses_single_ohlc_batch_when_available` — line 97.
- `test_cache_rate_limit_does_not_fan_out_to_historical_calls` — line 139.
- `test_opening_candidate_badge_green_red` — line 170.
- `test_opening_candidate_badge_red_green` — line 195.
- `test_opening_candidate_badge_rejects_red_red` — line 213.
- `test_opening_candidate_badge_accepts_green_green` — line 233.
- `test_opening_candidate_badge_handles_914_915_opposite_colors` — line 253.
- `test_opening_candidate_prefers_914_when_all_three_labels_exist` — line 273.
- `test_live_opening_window_keeps_first_five_candles_and_rest_replaces_websocket` — line 291.
- `test_quote_ticks_complete_previous_one_minute_candle` — line 325.
- `test_websocket_appends_completed_opening_candles` — line 344.
- `test_opposite_colors_below_four_times_volume_is_not_candidate` — line 361.
- `test_historical_volume_samples_skip_circuit_and_non_trading_days` — line 379.
- `test_historical_volume_samples_accept_914_fallback` — line 405.
- `test_cache_opening_volume_average_persists_samples_and_checks_today` — line 416.
- `test_volume_average_cache_succeeds_before_opening_pair_is_complete` — line 449.
- `test_snapshot_pins_candidates_first_and_marks_fno` — line 482.
- `test_volume_cache_stops_batch_on_expired_token` — line 505.
- `test_backtest_date_calculates_candidate_and_fno_badge` — line 531.
- `test_backtest_date_rejects_dates_older_than_sixty_days` — line 574.
- `test_backtest_non_trading_date_returns_stock_error` — line 582.

## tests/test_second_candle_pdl.py

2 test function declarations.

- `test_second_pdl_cross_live_backtest_and_schema` — line 22.
- `test_second_cross_waits_for_close_and_requires_current_daily_levels` — line 41.

## tests/test_security.py

10 test function declarations.

- `test_host_origin_and_public_schema` — line 21.
- `test_bad_bodies_are_rejected_before_handlers` — line 43.
- `test_header_url_method_bounds_and_private_files` — line 50.
- `test_validation_never_echoes_password_or_totp` — line 60.
- `test_persistent_account_login_limit_and_untrusted_forwarded_ip` — line 68.
- `test_request_flood_limit_and_bounded_bucket_memory` — line 85.
- `test_password_work_is_bounded_and_otp_budget_survives_new_challenges` — line 96.
- `test_sql_injection_is_data_not_a_query` — line 118.
- `test_streamed_body_size_and_timeout` — line 128.
- `test_stored_script_payloads_render_as_text` — line 148.

## tests/test_setup_price_filters.py

13 test function declarations.

- `test_redwala_gap_and_strict_cross` — line 22.
- `test_redwala_either_distance_from_previous_close` — line 34.
- `test_redwala_opening_tolerance_boundary` — line 49.
- `test_tolerance_does_not_enable_parent_filter_or_affect_other_setups` — line 57.
- `test_pdhl_boundary` — line 68.
- `test_possible_open_previous_close_absolute_boundary` — line 77.
- `test_possible_open_gap_combines_with_pdhl` — line 87.
- `test_invalid_levels_unresolved_only_for_enabled_setup` — line 99.
- `test_preview_confirmed_scanner_backtest_and_save_agree` — line 128.
- `test_missing_levels_repair_reuses_candle_and_never_publishes_match` — line 165.
- `test_retest_unaffected_by_both_new_filters` — line 190.
- `test_old_config_defaults_off` — line 204.
- `test_redwala_required_daily_auth_error_keeps_original_error_and_stops_batch` — line 215.

## tests/test_staged_scan.py

11 test function declarations.

- `test_daily_first_only_survivors_need_minute_history_and_same_day_cache_reused` — line 50.
- `test_preparation_retries_missing_data_without_excluding_stock` — line 78.
- `test_persistent_preparation_failure_remains_unresolved` — line 95.
- `test_restart_reuses_today_cache_and_discards_previous_sessions` — line 112.
- `test_timer_publishes_provisional_match_without_next_trade_then_confirms` — line 138.
- `test_safe_volume_reject_skips_rest_but_missing_feed_is_confirmed` — line 164.
- `test_incomplete_apparent_reject_and_unresolved_only_retry_after_matches` — line 185.
- `test_idle_priority_context_does_not_block_preparation` — line 211.
- `test_priority_released_on_error` — line 221.
- `test_300_stock_universe_reduces_preparation_and_confirmation_requests` — line 229.
- `test_start_subscribes_all_stocks_including_daily_failures_for_redwala` — line 271.

## tests/test_turnover_filter.py

1 test function declarations.

- `test_three_crore_strict_boundary_in_live_backtest_and_counts` — line 14.

## tests/test_volume_settings.py

15 test function declarations.

- `test_invalid_settings` — line 22.
- `test_persistence_and_legacy_defaults` — line 27.
- `test_custom_daily_boundary_and_cache_recalculation` — line 44.
- `test_custom_filters_match_live_and_backtest` — line 59.
- `test_saving_rechecks_confirmed_candle_and_reopens_rejected_stocks` — line 83.
- `test_settings_keep_active_feed_and_signal_background_workers` — line 103.
- `test_slow_subscription_does_not_block_saves_or_snapshots_and_edits_coalesce` — line 115.
- `test_completed_confirmation_worker_wakes_for_settings_without_new_feed` — line 160.
- `test_save_rechecks_300_stocks_without_network_or_bulk_cache_write` — line 187.
- `test_backtest_keeps_one_settings_snapshot_when_live_changes` — line 198.
- `test_restart_recalculates_older_cache_without_refetching` — line 219.
- `test_local_volume_rejection_uses_selected_minimum` — line 230.
- `test_custom_turnover_strict_boundary_in_live_preview_confirmation_and_backtest` — line 252.
- `test_existing_volume_settings_receive_default_turnover` — line 279.
- `test_request_filter_snapshot_is_cleared_after_failed_backtest` — line 288.

## tests/test_dashboard.cjs

- circuit default hides low and unverified bands, preserves turnover and badge priority
- circuit toggle persists, toggles immediately, and never filters historical results
- corrupt or blocked storage defaults circuit filter ON; volume and maximum price still combine
- daily resistance settings validate, describe and submit all controls
- resistance badges remain Possible-only and receive turnover sorting priority
- API validation errors show the field and reason instead of object Object
- daily history warnings label Redwala as partial and preserve all failure details
- Redwala low-break badges appear only on Redwala in live and backtest
- PDL badge requires first-candle cross regardless of later breaks in live and backtest
- second-candle PDL badge appears only on Redwala in both views
- live breakout badges sort first, preserve other matches, and update as badges arrive
- complete Possible combination precedes three-or-four-badge Redwala, then remaining rows sort by turnover
- backtest sends opening scan mode
- backtest waits for selected monthly and two-day filters to save before running
- failed or timed-out filter save never starts a backtest
- invalid settings and an in-progress save block backtests
- turnover column, high-break badge and Retest Break scan render in both views
- filter summary reports the open-cross toggle and exact comparison
- new opening filters show exact rules in live summaries
- filter form submits both toggles and restores saved selections
- background config refresh preserves toggle drafts and typed credentials
- initial slow config load preserves fields edited while it runs
- late initial algo state and later polls preserve edited algo toggles
- stale config response cannot replace newly saved filter state
- setup-specific price controls round trip decimals and reject invalid percentages
- turnover captions use live settings and preserve each backtest threshold
- save completes without waiting for state polling or overwriting newer edits
- save timeout unlocks controls and explains uncertain persistence
- live table displays only qualified rows with correct badges and daily columns
- backtest filtering matches live and preserves failed-check diagnostics
- empty results use updated table spans and escape provider errors
- first-candle setup and crossing badges appear in live and backtest without a second candle
- under_3.5% badge uses the absolute opening gap in live and backtest, independently of the filter
- circuit distances display percentage, zero at the limit and missing states
- live matches are visible as awaiting confirmation without final badges or confirmed counts
- opening setups and algo start controls remain visible after 13:30 IST
- partial badge combinations sort only by first-candle turnover, preserving ties and setup selection
- explicit first direction overrides setup direction in the live confirmation
- dashboard absolute volume filter is strict, preserves badge priority and sorts by opening turnover
- dashboard volume settings survive reload and polling, reject invalid thresholds, and tolerate unavailable storage
- shared filters use a strict volume minimum and inclusive price maximum
- price filter survives reload and rejects invalid drafts without changing last applied setting
- backtest displays opening gap inputs separately from previous day change and warns about changed filters
- backtest refuses results when server did not use requested opening gap setting
- date inputs and candle labels use IST even across UTC and month boundaries
- price maximum preserves legacy saved values and includes below/equal prices

## tests/test_dashboard_browser.cjs

Standalone browser/test harness; inspect source for workflows.

