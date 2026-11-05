"""PHASE_01 routes (openapi-draft 0.6.0-draft). Every path is in the contract (route parity contract test)."""

from __future__ import annotations

from django.urls import URLPattern, path

from . import auth_views as A
from . import config_views as C
from . import document_views as D
from . import identity_views as I
from . import ops_views as O
from . import org_views as G
from . import workflow_views as W

U = "<uuid:{}>".format

urlpatterns: list[URLPattern] = [
    # auth / me
    path("auth/login", A.LoginView.as_view()),
    path("auth/mfa/verify", A.VerifyMfaView.as_view()),
    path("auth/mfa/step-up", A.StepUpMfaView.as_view()),
    path("auth/logout", A.LogoutView.as_view()),
    path("auth/session", A.CurrentSessionView.as_view()),
    path("auth/sessions", A.MySessionsView.as_view()),
    path("auth/sessions/<str:session_id>/revoke", A.RevokeMySessionView.as_view()),
    path("auth/password/change", A.ChangePasswordView.as_view()),
    path("auth/mfa/enrolment", A.MfaEnrolmentView.as_view()),
    path("auth/mfa/enrolment/confirm", A.MfaEnrolmentConfirmView.as_view()),
    path("me", A.MeView.as_view()),
    path("me/permissions", A.MyPermissionsView.as_view()),
    # admin identity
    path("admin/users", I.UsersView.as_view()),
    path(f"admin/users/{U('user_id')}", I.UserView.as_view()),
    path(f"admin/users/{U('user_id')}/disable", I.DisableUserView.as_view()),
    path(f"admin/users/{U('user_id')}/enable", I.EnableUserView.as_view()),
    path(f"admin/users/{U('user_id')}/unlock", I.UnlockUserView.as_view()),
    path(f"admin/users/{U('user_id')}/reset-password", I.ResetPasswordView.as_view()),
    path(f"admin/users/{U('user_id')}/reset-mfa", I.ResetMfaView.as_view()),
    path(f"admin/users/{U('user_id')}/sessions", I.UserSessionsView.as_view()),
    path(f"admin/users/{U('user_id')}/sessions/revoke-all", I.RevokeUserSessionsView.as_view()),
    path(f"admin/users/{U('user_id')}/effective-permissions", I.UserEffectivePermissionsView.as_view()),
    path("admin/permissions", I.PermissionsView.as_view()),
    path("admin/roles", I.RolesView.as_view()),
    path(f"admin/roles/{U('role_id')}", I.RoleView.as_view()),
    path(f"admin/roles/{U('role_id')}/activate", I.ActivateRoleView.as_view()),
    path(f"admin/roles/{U('role_id')}/retire", I.RetireRoleView.as_view()),
    path("admin/role-assignments", I.AssignmentsView.as_view()),
    path(f"admin/role-assignments/{U('assignment_id')}", I.AssignmentView.as_view()),
    path(f"admin/role-assignments/{U('assignment_id')}/revoke", I.RevokeAssignmentView.as_view()),
    # org
    path("org/tree", G.OrgTreeView.as_view()),
    path("org/units", G.UnitsView.as_view()),
    path(f"org/units/{U('unit_id')}", G.UnitView.as_view()),
    path(f"org/units/{U('unit_id')}/move", G.MoveUnitView.as_view()),
    path(f"org/units/{U('unit_id')}/deactivate", G.DeactivateUnitView.as_view()),
    path("org/positions", G.PositionsView.as_view()),
    path(f"org/positions/{U('position_id')}", G.PositionView.as_view()),
    path("org/position-assignments", G.PositionAssignmentsView.as_view()),
    path(
        f"org/position-assignments/{U('position_assignment_id')}/end",
        G.EndPositionAssignmentView.as_view(),
    ),
    # workflow
    path("workflow/tasks", W.TasksView.as_view()),
    path(f"workflow/tasks/{U('task_id')}", W.TaskView.as_view()),
    path(f"workflow/tasks/{U('task_id')}/start", W.StartTaskView.as_view()),
    path(f"workflow/tasks/{U('task_id')}/complete", W.CompleteTaskView.as_view()),
    path(f"workflow/tasks/{U('task_id')}/block", W.BlockTaskView.as_view()),
    path(f"workflow/tasks/{U('task_id')}/unblock", W.UnblockTaskView.as_view()),
    path(f"workflow/tasks/{U('task_id')}/reassign", W.ReassignTaskView.as_view()),
    path(f"workflow/tasks/{U('task_id')}/verify-close", W.VerifyCloseTaskView.as_view()),
    path(f"workflow/tasks/{U('task_id')}/cancel", W.CancelTaskView.as_view()),
    path("workflow/approvals", W.ApprovalsView.as_view()),
    path(f"workflow/approvals/{U('approval_id')}", W.ApprovalView.as_view()),
    path(f"workflow/approvals/{U('approval_id')}/approve", W.ApproveRequestView.as_view()),
    path(f"workflow/approvals/{U('approval_id')}/reject", W.RejectRequestView.as_view()),
    path(f"workflow/approvals/{U('approval_id')}/withdraw", W.WithdrawRequestView.as_view()),
    path(f"workflow/approvals/{U('approval_id')}/bootstrap-approve", W.BootstrapApproveRequestView.as_view()),
    path("workflow/definitions", W.DefinitionsView.as_view()),
    path(f"workflow/definitions/{U('definition_id')}", W.DefinitionView.as_view()),
    path(f"workflow/instances/{U('instance_id')}", W.InstanceView.as_view()),
    path(f"workflow/instances/{U('instance_id')}/cancel", W.CancelInstanceView.as_view()),
    # audit
    path("audits", O.AuditEventsView.as_view()),
    path("audits/integrity", O.AuditIntegrityView.as_view()),
    path(f"audits/{U('audit_event_id')}", O.AuditEventView.as_view()),
    # jobs / health
    path("admin/health", O.HealthDetailView.as_view()),
    path("admin/job-definitions", O.JobDefinitionsView.as_view()),
    path("admin/jobs", O.JobsView.as_view()),
    path(f"admin/jobs/{U('job_id')}", O.JobView.as_view()),
    path(f"admin/jobs/{U('job_id')}/request-cancel", O.RequestJobCancelView.as_view()),
    # documents
    path("documents", D.DocumentsView.as_view()),
    path(f"documents/{U('document_id')}", D.DocumentView.as_view()),
    path(f"documents/{U('document_id')}/revisions", D.RevisionsView.as_view()),
    path(f"documents/{U('document_id')}/revisions/{U('revision_id')}", D.RevisionView.as_view()),
    path(
        f"documents/{U('document_id')}/revisions/{U('revision_id')}/content", D.RevisionContentView.as_view()
    ),
    path(
        f"documents/{U('document_id')}/revisions/{U('revision_id')}/submit-review",
        D.SubmitRevisionView.as_view(),
    ),
    path(
        f"documents/{U('document_id')}/revisions/{U('revision_id')}/approve", D.ApproveRevisionView.as_view()
    ),
    path(f"documents/{U('document_id')}/revisions/{U('revision_id')}/reject", D.RejectRevisionView.as_view()),
    # parameters / dynamic fields
    path("admin/parameters", C.ParametersView.as_view()),
    path("admin/parameters/<str:parameter_key>", C.ParameterView.as_view()),
    path("admin/parameters/<str:parameter_key>/values", C.ParameterValuesView.as_view()),
    path(
        f"admin/parameters/<str:parameter_key>/values/{U('value_revision_id')}/publish",
        C.PublishValueView.as_view(),
    ),
    path("admin/dynamic-fields", C.DynamicFieldsView.as_view()),
    path("admin/dynamic-fields/<str:field_key>", C.DynamicFieldView.as_view()),
]
