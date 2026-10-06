"""Accessible, compact Vega-Lite charts using Streamlit's existing renderer."""
from __future__ import annotations

import copy

GREEN = "#13795B"
INK = "#284936"
MUTED = "#667A6D"
COLORS = [GREEN, "#A46A1D", "#AC5149", "#567CA5", "#83948A"]
PAYMENT_COLORS = [GREEN, "#A46A1D", "#AC5149", "#567CA5", "#83948A"]


def _spec():
    return {"$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "background": "transparent", "padding": {"left": 8, "right": 8, "top": 10, "bottom": 10},
            "config": {"view": {"stroke": None},
                       "axis": {"labelColor": MUTED, "titleColor": INK, "labelFontSize": 11,
                                "titleFontSize": 11, "gridColor": "#E7EEE8", "domain": False,
                                "tickColor": "#D6E2D9", "titlePadding": 12},
                       "legend": {"labelColor": MUTED, "titleColor": INK, "labelFontSize": 11,
                                  "orient": "bottom", "direction": "horizontal", "columns": 2, "labelLimit": 130}}}


def exposure_spec(analytics):
    rows = copy.deepcopy(analytics["exposure_by_dpd"])
    spec = _spec()
    spec.update({"data": {"values": rows}, "height": 185,
                 "params": [{"name": "exposure_hover", "select": {"type": "point", "fields": ["bucket"], "on": "pointerover", "clear": "pointerout"}}],
                 "mark": {"type": "bar", "cornerRadiusEnd": 5},
                 "encoding": {
                     "y": {"field": "bucket", "type": "ordinal", "sort": [r["bucket"] for r in rows],
                           "axis": {"title": None, "labelLimit": 130}},
                     "x": {"field": "balance", "type": "quantitative", "axis": {"title": "Outstanding balance · INR", "format": "~s"}},
                     "color": {"field": "bucket", "type": "nominal", "scale": {"domain": [r["bucket"] for r in rows], "range": COLORS[:4]}, "legend": None},
                     "opacity": {"condition": {"param": "exposure_hover", "value": 1}, "value": .55},
                     "tooltip": [{"field": "bucket", "title": "Loan repayment bucket"},
                                 {"field": "balance", "type": "quantitative", "title": "Outstanding INR", "format": ",.0f"},
                                 {"field": "loans", "type": "quantitative", "title": "Active loans"},
                                 {"field": "customers", "type": "quantitative", "title": "Customers in this bucket"}]}})
    return spec


def action_mix_spec(analytics):
    rows = copy.deepcopy(analytics["action_mix"])
    spec = _spec()
    spec.update({"data": {"values": rows}, "height": 185,
                 "mark": {"type": "bar", "cornerRadiusEnd": 5},
                 "encoding": {
                     "y": {"field": "action", "type": "ordinal", "sort": [r["action"] for r in rows],
                           "axis": {"title": None, "labelLimit": 140}},
                     "x": {"field": "customers", "type": "quantitative", "axis": {"title": "Customer relationships", "tickMinStep": 1}},
                     "color": {"field": "action", "type": "nominal", "scale": {"domain": [r["action"] for r in rows], "range": COLORS}, "legend": None},
                     "tooltip": [{"field": "action", "title": "Recommended intervention"},
                                 {"field": "customers", "type": "quantitative", "title": "Customers"},
                                 {"field": "share", "type": "quantitative", "title": "Portfolio share", "format": ".0%"}]}})
    return spec


def driver_spec(analytics):
    rows = copy.deepcopy(analytics["heuristic_drivers"])
    spec = _spec()
    spec.update({"data": {"values": rows}, "height": 170,
                 "mark": {"type": "bar", "cornerRadiusEnd": 5, "color": GREEN},
                 "encoding": {
                     "y": {"field": "driver", "type": "ordinal", "sort": [r["driver"] for r in rows],
                           "axis": {"title": None, "labelLimit": 175}},
                     "x": {"field": "points", "type": "quantitative", "scale": {"domain": [0, 40]},
                           "axis": {"title": "Contribution to heuristic priority · points"}},
                     "tooltip": [{"field": "driver", "title": "Observed driver"},
                                 {"field": "points", "type": "quantitative", "title": "Priority points", "format": ".1f"},
                                 {"field": "rule", "title": "Demonstration rule"},
                                 {"field": "observed", "title": "Observed in current records"}]}})
    return spec


def relationship_timeline_spec(analytics):
    """Aligned time axes compare actual repayment records with conversations."""
    payment_rows = [{**row, "kind": "repayment", "when": row["month"]} for row in analytics["payment_history"]]
    conversation_rows = [{**row, "kind": "conversation", "when": row["timestamp"]} for row in analytics["conversation_history"]]
    data = payment_rows + conversation_rows
    domain = sorted({r["when"] for r in data})
    x = {"field": "when", "type": "temporal", "axis": {"format": "%b %y", "title": None, "labelAngle": -30, "tickCount": 6}}
    if len(domain) > 1:
        x["scale"] = {"domain": [domain[0], domain[-1]]}
    spec = _spec()
    spec.update({"data": {"values": data}, "spacing": 28,
                 "resolve": {"scale": {"x": "shared", "color": "independent"}},
                 "vconcat": [
                     {"height": 155, "transform": [{"filter": "datum.kind === 'repayment'"}],
                      "mark": {"type": "bar", "size": 13, "cornerRadiusTopLeft": 3, "cornerRadiusTopRight": 3},
                      "encoding": {"x": copy.deepcopy(x),
                                   "y": {"field": "payments", "type": "quantitative", "axis": {"title": "Repayment records", "tickMinStep": 1}, "stack": "zero"},
                                   "color": {"field": "status", "type": "nominal", "scale": {"domain": ["On time", "Late", "Bounced", "Pending", "Other"], "range": PAYMENT_COLORS}, "legend": {"title": None}},
                                   "tooltip": [{"field": "when", "type": "temporal", "title": "Due month", "format": "%b %Y"},
                                               {"field": "status", "title": "Recorded status"},
                                               {"field": "payments", "type": "quantitative", "title": "Payment records"},
                                               {"field": "amount_due", "type": "quantitative", "title": "Due INR", "format": ",.0f"},
                                               {"field": "amount_paid", "type": "quantitative", "title": "Paid INR", "format": ",.0f"}]}},
                     {"height": 115, "transform": [{"filter": "datum.kind === 'conversation'"}],
                      "layer": [{"mark": {"type": "rule", "color": "#D7E1DA", "strokeDash": [4, 4]},
                                 "encoding": {"y": {"datum": 0}}},
                                {"mark": {"type": "point", "filled": True, "size": 95},
                                 "encoding": {"x": copy.deepcopy(x),
                                              "y": {"field": "sentiment", "type": "quantitative", "scale": {"domain": [-1, 1]},
                                                    "axis": {"title": "Conversation tone", "values": [-1, 0, 1]}},
                                              "color": {"field": "channel", "type": "nominal", "scale": {"range": [GREEN, "#567CA5", "#A46A1D", "#AC5149"]}, "legend": {"title": "Recorded channel"}},
                                              "tooltip": [{"field": "when", "type": "temporal", "title": "Conversation date", "format": "%d %b %Y"},
                                                          {"field": "channel", "title": "Channel"}, {"field": "intent", "title": "Observed intent"},
                                                          {"field": "sentiment", "type": "quantitative", "title": "Heuristic tone", "format": ".2f"},
                                                          {"field": "evidence_id", "title": "Source ID"}, {"field": "excerpt", "title": "Customer evidence"}]}}]}
                 ]})
    return spec


def signal_spec(analytics):
    spec = _spec()
    rows = copy.deepcopy(analytics["driver_prevalence"])
    spec.update({"data": {"values": rows}, "height": 165, "mark": {"type": "bar", "color": "#567CA5", "cornerRadiusEnd": 5},
                 "encoding": {"y": {"field": "signal", "type": "ordinal", "sort": [r["signal"] for r in rows], "axis": {"title": None, "labelLimit": 160}},
                              "x": {"field": "customers", "type": "quantitative", "axis": {"title": "Customers with this observed signal", "tickMinStep": 1}},
                              "tooltip": [{"field": "signal", "title": "Recorded signal"}, {"field": "customers", "type": "quantitative", "title": "Customers"}]}})
    return spec


def render_portfolio_charts(analytics, key_prefix="portfolio"):
    import streamlit as st

    exposure, interventions = st.columns(2, gap="large")
    with exposure:
        st.markdown("**Repayment exposure**")
        st.vega_lite_chart(exposure_spec(analytics), width="stretch", theme=None,
                           key=key_prefix + "_exposure", alt="Active loan outstanding balances in INR grouped by loan-level days past due.")
        st.caption("Active-loan balances, grouped by each loan’s recorded overdue days. Customer counts can span buckets.")
    with interventions:
        st.markdown("**Recommended intervention mix**")
        st.vega_lite_chart(action_mix_spec(analytics), width="stretch", theme=None,
                           key=key_prefix + "_actions", alt="Customer counts by the actual policy recommendation, including monitor and policy hold.")
        st.caption("Recommendations awaiting review. Monitor or policy hold does not mean contact is eligible.")


def render_relationship_timeline(analytics, key_prefix="relationship"):
    import streamlit as st

    if not analytics["payment_history"] and not analytics["conversation_history"]:
        st.caption("No observed repayment or conversation history is available in the last 12 calendar months.")
        return
    st.vega_lite_chart(relationship_timeline_spec(analytics), width="stretch", theme=None,
                       key=key_prefix + "_timeline", alt="Aligned timelines compare monthly recorded repayment status with dated customer conversation signals.")
    st.caption("Recorded history over the last 12 calendar months. Conversation tone is a heuristic signal, not a verified emotion or a cause of repayment behaviour. Future-dated records are excluded.")


def render_driver_chart(analytics, key_prefix="drivers"):
    import streamlit as st

    st.vega_lite_chart(driver_spec(analytics), width="stretch", theme=None,
                       key=key_prefix + "_priority", alt="Contribution of four explicit rules to this customer's illustrative retention priority.")
    st.caption(f'Current illustrative priority: {analytics["heuristic_priority_points"]}/100. These are deterministic rule contributions, not a trained prediction or churn probability.')


def render_intervention_matrix(rows, key_prefix="comparison"):
    import streamlit as st

    table = [{"New context": row["label"], "Next intervention": row["after_action"],
              "Offer effect": row["offer_change"], "Action changes": "Yes" if row["action_changed"] else "No"} for row in rows]
    st.dataframe(table, hide_index=True, width="stretch", key=key_prefix + "_matrix")
    st.caption("Each row executes the current policy against a fictional evidence overlay. No customer record, contact preference or financial term is saved.")


def render_governance(analytics, key_prefix="governance"):
    import streamlit as st

    governance = analytics["governance"]
    columns = st.columns(3)
    columns[0].metric("Complete lending context", f'{governance.get("complete_profiles", 0)}/{governance["customers"]}')
    columns[1].metric("Recent conversation context", f'{governance.get("signal_within_lookback", 0)}/{governance["customers"]}')
    columns[2].metric("Recommendations with citations", f'{governance.get("actions_with_citations", 0)}/{governance.get("actions_for_review", 0)}')
    st.caption("Recency uses the current action’s lookback window: support 45 days, retention 60 days, growth 90 days, other cases 30 days.")
    st.vega_lite_chart(signal_spec(analytics), width="stretch", theme=None, key=key_prefix + "_signals",
                       alt="Portfolio counts for observed hardship, transfer intent, negative conversation tone, missing context and contact restrictions.")
    with st.expander("Coverage and limitations"):
        coverage = [{"Customer segment": row["segment"], "Relationships": row["customers"],
                     "Contact permitted": row["contact_permitted"], "Proposals for review": row["actions_for_review"],
                     "Proposal share": f'{row["review_share"]:.0%}'} for row in analytics["segment_coverage"]]
        st.dataframe(coverage, hide_index=True, width="stretch")
        st.caption(governance["fairness_note"])
        st.caption("The prototype does not establish model accuracy, regulatory compliance, financial impact or production readiness.")
