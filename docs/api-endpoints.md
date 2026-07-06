# ClickMe API 엔드포인트 (자동 생성)

> 이 파일은 `backend/scripts/gen_docs.py`가 코드에서 **자동 생성**합니다. 직접 편집하지 말고 소스를 고친 뒤 스크립트를 다시 실행하세요(커밋 시 pre-commit 훅이 자동 갱신).

총 **184개** 엔드포인트 · **17개** 그룹.

## admin

| Method | Path | Name |
|---|---|---|
| GET | `/api/admin/chats` | list_chats |
| DELETE | `/api/admin/companies/{org_id}` | delete_company |
| DELETE | `/api/admin/companies/{org_id}/purge` | purge_company |
| POST | `/api/admin/companies/{org_id}/restore` | restore_company |
| GET | `/api/admin/generations` | list_generations |
| GET | `/api/admin/organizations` | list_organizations |
| GET | `/api/admin/simulations` | list_simulations |
| GET | `/api/admin/users` | list_users |
| POST | `/api/admin/users` | create_user |
| DELETE | `/api/admin/users/{user_id}` | delete_user |
| PATCH | `/api/admin/users/{user_id}` | update_user |
| DELETE | `/api/admin/users/{user_id}/purge` | purge_user |
| POST | `/api/admin/users/{user_id}/restore` | restore_user |

## ads

| Method | Path | Name |
|---|---|---|
| POST | `/api/ads/analyze/image` | analyze_image |
| POST | `/api/ads/analyze/text` | analyze_text |
| POST | `/api/ads/compare` | compare_ads |
| POST | `/api/ads/upload` | upload_ad |

## assistant

| Method | Path | Name |
|---|---|---|
| POST | `/api/assistant/chat` | chat_complete |

## auth

| Method | Path | Name |
|---|---|---|
| POST | `/api/auth/change-password` | change_password |
| GET | `/api/auth/me` | me |
| PATCH | `/api/auth/me` | update_me |

## automation

| Method | Path | Name |
|---|---|---|
| GET | `/api/automation/runs` | list_automation_runs |

## billing

| Method | Path | Name |
|---|---|---|
| GET | `/api/billing/balance` | get_balance |
| POST | `/api/billing/cancel` | cancel_payment |
| POST | `/api/billing/confirm` | confirm_payment |
| GET | `/api/billing/history` | get_history |
| POST | `/api/billing/orders` | create_order |

## chat

| Method | Path | Name |
|---|---|---|
| POST | `/api/chat/approve` | chat_approve |
| POST | `/api/chat/complete` | chat_complete |
| POST | `/api/chat/feedback` | chat_feedback |
| GET | `/api/chat/image` | proxy_chat_image |
| POST | `/api/chat/image` | upload_chat_image |
| GET | `/api/chat/kb-chunk` | get_kb_chunk |
| POST | `/api/chat/keywords` | suggest_keywords |
| GET | `/api/chat/loop-state` | chat_loop_state |
| PATCH | `/api/chat/messages/{message_id}/pin` | pin_chat_message |
| GET | `/api/chat/notifications` | list_notifications |
| GET | `/api/chat/report` | chat_report |
| GET | `/api/chat/result-summary` | chat_result_summary |
| GET | `/api/chat/sessions` | list_sessions |
| POST | `/api/chat/sessions` | create_session |
| DELETE | `/api/chat/sessions/{session_id}` | delete_session |
| GET | `/api/chat/sessions/{session_id}/messages` | get_session_messages |
| POST | `/api/chat/sessions/{session_id}/read` | mark_session_read |
| POST | `/api/chat/sim-batch` | chat_sim_batch |
| GET | `/api/chat/templates` | list_templates |
| POST | `/api/chat/templates` | create_template |
| POST | `/api/chat/widget-messages` | append_widget_messages |

## company

| Method | Path | Name |
|---|---|---|
| GET | `/api/company/generations` | list_company_generations |
| GET | `/api/company/members` | list_members |
| POST | `/api/company/members` | create_member |
| DELETE | `/api/company/members/{member_id}` | delete_member |
| PATCH | `/api/company/members/{member_id}` | update_member |
| PATCH | `/api/company/members/{member_id}/team` | assign_member_team |
| GET | `/api/company/my-team-members` | my_team_members |
| GET | `/api/company/org` | get_my_org |
| PATCH | `/api/company/projects/{project_id}/team` | assign_project_team |
| GET | `/api/company/simulations` | list_company_simulations |
| GET | `/api/company/teams` | list_teams |
| POST | `/api/company/teams` | create_team |
| DELETE | `/api/company/teams/{team_id}` | delete_team |

## dashboard

| Method | Path | Name |
|---|---|---|
| GET | `/api/dashboard/recent-generations` | get_recent_generations |
| GET | `/api/dashboard/recent-simulations` | get_recent_simulations |
| GET | `/api/dashboard/stats` | get_stats |

## debate

| Method | Path | Name |
|---|---|---|
| POST | `/api/debate/analyze` | analyze_reactions |
| GET | `/api/debate/by-simulation/{simulation_id}` | list_sessions |
| GET | `/api/debate/by-simulation/{simulation_id}/report` | get_saved_report |
| POST | `/api/debate/start` | start_debate |
| POST | `/api/debate/topics` | debate_topics |
| GET | `/api/debate/{debate_id}/detail` | get_session |
| POST | `/api/debate/{run_id}/question` | ask_question |
| GET | `/api/debate/{run_id}/report.pdf` | download_report_pdf |
| GET | `/api/debate/{run_id}/result` | debate_result |
| GET | `/api/debate/{run_id}/stream` | stream_debate |

## generator

| Method | Path | Name |
|---|---|---|
| GET | `/api/generator/brand-kits` | list_brand_kits |
| POST | `/api/generator/brand-kits` | create_brand_kit |
| DELETE | `/api/generator/brand-kits/{kit_id}` | delete_brand_kit |
| PUT | `/api/generator/brand-kits/{kit_id}` | update_brand_kit |
| GET | `/api/generator/brand-profile` | get_brand_profile |
| POST | `/api/generator/brand-profile` | update_brand_profile |
| GET | `/api/generator/candidates/{candidate_id}/render` | render_candidate |
| GET | `/api/generator/generations` | list_generations |
| POST | `/api/generator/generations` | create_generation |
| POST | `/api/generator/generations/loop` | start_generation_loop |
| GET | `/api/generator/generations/loop/{loop_id}` | get_generation_loop |
| GET | `/api/generator/generations/loop/{loop_id}/stream` | stream_generation_loop |
| GET | `/api/generator/generations/{generation_id}` | get_generation |
| GET | `/api/generator/generations/{generation_id}/download-zip` | download_generation_zip |
| POST | `/api/generator/generations/{generation_id}/publish` | publish_candidate |
| POST | `/api/generator/generations/{generation_id}/select` | select_candidate |
| GET | `/api/generator/generations/{generation_id}/stream` | stream_generation |
| GET | `/api/generator/image` | proxy_image |
| GET | `/api/generator/instagram-status` | instagram_status |
| GET | `/api/generator/langsmith-status` | langsmith_status |
| POST | `/api/generator/logo` | upload_logo |
| POST | `/api/generator/product-image` | upload_product_image |

## health

| Method | Path | Name |
|---|---|---|
| GET | `/health` | health_check |

## inquiries

| Method | Path | Name |
|---|---|---|
| POST | `/api/inquiries` | create_inquiry |

## management

| Method | Path | Name |
|---|---|---|
| POST | `/api/management/ad-image` | upload_ad_image |
| POST | `/api/management/ad-preview` | ad_preview |
| POST | `/api/management/anomaly/notify-scan` | anomaly_notify_scan |
| GET | `/api/management/anomaly/scan` | anomaly_scan |
| POST | `/api/management/approve` | approve_proposal |
| POST | `/api/management/assistant` | management_assistant |
| GET | `/api/management/audit` | get_audit |
| GET | `/api/management/budget` | get_budget |
| POST | `/api/management/budget/limit` | set_budget_limit |
| GET | `/api/management/budget/rebalance-proposal` | budget_rebalance_proposal |
| GET | `/api/management/calibration/anchors` | calibration_anchors |
| GET | `/api/management/campaign-policy` | campaign_policy |
| POST | `/api/management/campaign-proposals/from-candidate` | from_candidate |
| POST | `/api/management/campaign-proposals/from-simulation` | from_simulation |
| GET | `/api/management/campaign-proposals/name-suggestions` | campaign_name_suggestions |
| GET | `/api/management/campaigns` | list_campaigns |
| POST | `/api/management/campaigns/create-proposal` | create_campaign_proposal |
| DELETE | `/api/management/campaigns/{campaign_id}` | delete_campaign |
| GET | `/api/management/campaigns/{campaign_id}` | get_campaign |
| POST | `/api/management/campaigns/{campaign_id}/activate` | activate_campaign |
| POST | `/api/management/campaigns/{campaign_id}/budget-commit` | budget_commit |
| POST | `/api/management/campaigns/{campaign_id}/budget-proposal` | budget_proposal |
| GET | `/api/management/campaigns/{campaign_id}/creative-image` | proxy_creative_image |
| GET | `/api/management/campaigns/{campaign_id}/creatives` | get_campaign_creatives |
| GET | `/api/management/campaigns/{campaign_id}/delivery-status` | delivery_status |
| GET | `/api/management/campaigns/{campaign_id}/demographics` | get_campaign_demographics |
| PUT | `/api/management/campaigns/{campaign_id}/kpi-override` | put_kpi_override |
| GET | `/api/management/campaigns/{campaign_id}/leads` | campaign_leads |
| POST | `/api/management/campaigns/{campaign_id}/link-simulation` | link_simulation |
| GET | `/api/management/campaigns/{campaign_id}/outcome` | get_campaign_outcome |
| POST | `/api/management/campaigns/{campaign_id}/pause` | pause_campaign |
| GET | `/api/management/campaigns/{campaign_id}/platforms` | get_campaign_platforms |
| POST | `/api/management/campaigns/{campaign_id}/replace-creative-proposal` | replace_creative_proposal |
| GET | `/api/management/campaigns/{campaign_id}/sync` | sync_campaign |
| GET | `/api/management/campaigns/{campaign_id}/targeting` | get_campaign_targeting |
| GET | `/api/management/compare` | compare_one |
| GET | `/api/management/compare/before-after` | compare_before_after |
| GET | `/api/management/compare/board` | compare_board |
| GET | `/api/management/created-campaigns` | created_campaigns |
| POST | `/api/management/execute` | execute |
| GET | `/api/management/execution/history` | execution_history_endpoint |
| GET | `/api/management/kb/eval/faithfulness` | kb_eval_faithfulness |
| POST | `/api/management/kb/eval/generate` | kb_eval_generate |
| GET | `/api/management/kb/eval/run` | kb_eval_run |
| POST | `/api/management/kb/refresh` | kb_refresh |
| GET | `/api/management/kpi-overrides` | list_kpi_overrides |
| GET | `/api/management/meta/callback` | meta_callback |
| GET | `/api/management/meta/connect` | meta_connect |
| GET | `/api/management/notifications` | list_notifications |
| POST | `/api/management/notifications/read` | read_notifications |
| GET | `/api/management/notifications/stream` | notifications_stream |
| POST | `/api/management/notifications/{notification_id}/consult` | consult_from_notification |
| POST | `/api/management/notifications/{notification_id}/resolve` | resolve_notification |
| POST | `/api/management/re-evaluate` | re_evaluate |
| POST | `/api/management/re-evaluate/executed` | mark_rung_executed |
| POST | `/api/management/re-evaluate/rejected` | mark_rung_rejected |
| POST | `/api/management/regenerate` | regenerate |
| GET | `/api/management/report/weekly` | weekly_report |
| GET | `/api/management/run` | run_detection |

## personas

| Method | Path | Name |
|---|---|---|
| POST | `/api/personas/generate` | generate_personas |

## projects

| Method | Path | Name |
|---|---|---|
| GET | `/api/projects` | list_projects |
| POST | `/api/projects` | create_project |
| DELETE | `/api/projects/generations/{generation_id}` | delete_generation |
| GET | `/api/projects/generations/{generation_id}` | get_generation_detail |
| POST | `/api/projects/generations/{generation_id}/restore` | restore_generation |
| DELETE | `/api/projects/simulations/{simulation_id}` | delete_simulation |
| GET | `/api/projects/simulations/{simulation_id}` | get_simulation_detail |
| POST | `/api/projects/simulations/{simulation_id}/restore` | restore_simulation |
| GET | `/api/projects/trash` | list_trash |
| DELETE | `/api/projects/{project_id}` | delete_project |
| GET | `/api/projects/{project_id}` | get_project |
| GET | `/api/projects/{project_id}/generations` | list_project_generations |
| POST | `/api/projects/{project_id}/restore` | restore_project |
| GET | `/api/projects/{project_id}/simulations` | list_project_simulations |
| POST | `/api/projects/{project_id}/trash/purge` | purge_trash |
| POST | `/api/projects/{project_id}/trash/restore` | restore_trash |

## simulation

| Method | Path | Name |
|---|---|---|
| POST | `/api/simulation` | start_simulation |
| GET | `/api/simulation/categories` | get_categories |
| GET | `/api/simulation/check-image` | check_image |
| POST | `/api/simulation/compare` | compare_simulation |
| GET | `/api/simulation/image` | proxy_ad_image |
| POST | `/api/simulation/run` | run_simulation |
| GET | `/api/simulation/{run_id}/result` | get_simulation_result |
| GET | `/api/simulation/{run_id}/result/analysis` | get_simulation_result_analysis |
| GET | `/api/simulation/{run_id}/stream` | stream_simulation |
| GET | `/api/simulation/{simulation_id}/db-result` | get_simulation_db_result |
