"""PHASE_02 routes (openapi-draft 0.8.0-draft, step 02.4). Every path is in the contract (route parity)."""

from __future__ import annotations

from django.urls import URLPattern, path

from . import commercial_views as C
from . import identity_views as I

U = "<uuid:{}>".format

urlpatterns: list[URLPattern] = [
    # identity: customers, brands
    path("identity/customers", I.CustomersView.as_view()),
    path(f"identity/customers/{U('customer_id')}", I.CustomerView.as_view()),
    path(f"identity/customers/{U('customer_id')}/brands", I.CustomerBrandsView.as_view()),
    path(f"identity/customers/{U('customer_id')}/brands/{U('brand_id')}", I.CustomerBrandView.as_view()),
    # identity: classes, products, styles
    path("identity/product-classes", I.ProductClassesView.as_view()),
    path("identity/products", I.ProductsView.as_view()),
    path(f"identity/products/{U('product_id')}", I.ProductView.as_view()),
    path(f"identity/products/{U('product_id')}/styles", I.ProductStylesView.as_view()),
    path(f"identity/styles/{U('style_id')}", I.StyleView.as_view()),
    path(f"identity/styles/{U('style_id')}/revisions", I.StyleRevisionsView.as_view()),
    path(
        f"identity/styles/{U('style_id')}/revisions/{U('style_revision_id')}/activate",
        I.ActivateStyleRevisionView.as_view(),
    ),
    path(f"identity/styles/{U('style_id')}/tracking", I.StyleTrackingView.as_view()),
    path("identity/style-suggestions", I.StyleSuggestionsView.as_view()),
    # identity: product codes, code rule revisions
    path("identity/product-codes/validate", I.ValidateProductCodeView.as_view()),
    path("identity/product-codes/preview", I.PreviewProductCodeView.as_view()),
    path("identity/product-codes", I.ProductCodesView.as_view()),
    path(f"identity/product-codes/{U('product_code_id')}", I.ProductCodeView.as_view()),
    path("identity/code-rule-revisions", I.CodeRulesView.as_view()),
    path(f"identity/code-rule-revisions/{U('rule_revision_id')}", I.CodeRuleView.as_view()),
    path(
        f"identity/code-rule-revisions/{U('rule_revision_id')}/golden-cases",
        I.CodeRuleGoldenCasesView.as_view(),
    ),
    path(
        f"identity/code-rule-revisions/{U('rule_revision_id')}/submit-review", I.SubmitCodeRuleView.as_view()
    ),
    path(f"identity/code-rule-revisions/{U('rule_revision_id')}/approve", I.ApproveCodeRuleView.as_view()),
    path(f"identity/code-rule-revisions/{U('rule_revision_id')}/reject", I.RejectCodeRuleView.as_view()),
    path(f"identity/code-rule-revisions/{U('rule_revision_id')}/activate", I.ActivateCodeRuleView.as_view()),
    # identity: serials, external references, history
    path("identity/serials", I.SerialsView.as_view()),
    path(f"identity/serials/{U('serial_id')}", I.SerialView.as_view()),
    path(f"identity/serials/{U('serial_id')}/snapshots", I.SerialSnapshotsView.as_view()),
    path(f"identity/serials/{U('serial_id')}/tracking", I.SerialTrackingView.as_view()),
    path("identity/external-refs", I.ExternalRefsView.as_view()),
    path(f"identity/external-refs/{U('external_ref_id')}/end", I.EndExternalRefView.as_view()),
    path("identity/historical-order-records", I.HistoricalRecordsView.as_view()),
    # commercial: orders
    path("commercial/customer-orders", C.CustomerOrdersView.as_view()),
    path(f"commercial/customer-orders/{U('order_id')}", C.CustomerOrderView.as_view()),
    path(f"commercial/customer-orders/{U('order_id')}/lines", C.CustomerOrderLinesView.as_view()),
    path(
        f"commercial/customer-orders/{U('order_id')}/lines/{U('line_id')}", C.CustomerOrderLineView.as_view()
    ),
    path(
        f"commercial/customer-orders/{U('order_id')}/lines/{U('line_id')}/remove",
        C.RemoveCustomerOrderLineView.as_view(),
    ),
    path(f"commercial/customer-orders/{U('order_id')}/validate", C.ValidateCustomerOrderView.as_view()),
    path(f"commercial/customer-orders/{U('order_id')}/reopen", C.ReopenCustomerOrderView.as_view()),
    path(f"commercial/customer-orders/{U('order_id')}/cancel", C.CancelCustomerOrderView.as_view()),
    path(f"commercial/customer-orders/{U('order_id')}/confirm", C.ConfirmCustomerOrderView.as_view()),
    path(f"commercial/customer-orders/{U('order_id')}/release-to-plan", C.ReleaseCustomerOrderView.as_view()),
    path(f"commercial/customer-orders/{U('order_id')}/versions", C.CustomerOrderVersionsView.as_view()),
    path(
        f"commercial/customer-orders/{U('order_id')}/versions/<int:order_version>",
        C.CustomerOrderVersionView.as_view(),
    ),
    # commercial: change requests
    path("commercial/change-requests", C.ChangeRequestsView.as_view()),
    path(f"commercial/change-requests/{U('change_request_id')}", C.ChangeRequestView.as_view()),
    path(f"commercial/change-requests/{U('change_request_id')}/impact", C.ChangeRequestImpactView.as_view()),
    path(f"commercial/change-requests/{U('change_request_id')}/submit", C.SubmitChangeRequestView.as_view()),
    path(
        f"commercial/change-requests/{U('change_request_id')}/withdraw", C.WithdrawChangeRequestView.as_view()
    ),
    path(f"commercial/change-requests/{U('change_request_id')}/decide", C.DecideChangeRequestView.as_view()),
    path(
        f"commercial/change-requests/{U('change_request_id')}/planning-decision",
        C.PlanningDecideChangeRequestView.as_view(),
    ),
    path(f"commercial/change-requests/{U('change_request_id')}/apply", C.ApplyChangeRequestView.as_view()),
]
