#!/usr/bin/env python3
"""
visualize_workflow.py — Generate Mermaid visualizations for workflow compositions.

Outputs:
  - Mermaid diagram source (.mmd) for each variant
  - Variant comparison overlay
  - Workflow context graph (upstream/downstream connections)

v1.10.2: Simplified — removed execution_logger, removed Graphviz DOT/PNG generation
(scientific-visualization skill handles that), kept Mermaid as primary output.
"""

import json
import re
from pathlib import Path
from datetime import datetime


# ─── Color Scheme ───
COLORS = {
    "hw_fill": "#4A90D9",
    "hw_stroke": "#2C5F8A",
    "sw_fill": "#5CB85C",
    "sw_stroke": "#3D7A3D",
    "qc_fill": "#F0AD4E",
    "qc_stroke": "#D48A1A",
    "pass_color": "#28A745",
    "fail_color": "#DC3545",
    "edge_color": "#333333",
    "text_color": "white",
}

VARIANT_COLORS = [
    "#E67E22", "#9B59B6", "#1ABC9C", "#E74C3C",
    "#3498DB", "#2ECC71", "#F39C12", "#8E44AD",
]

# ─── Component Color Scheme (for enhanced UO visualization) ───
COMPONENT_COLORS = {
    "input":       {"fill": "#A8D8EA", "stroke": "#5B9BD5", "text": "#1A1A1A"},
    "output":      {"fill": "#FFD3B6", "stroke": "#E88D4F", "text": "#1A1A1A"},
    "equipment":   {"fill": "#D5A6E6", "stroke": "#8E44AD", "text": "#1A1A1A"},
    "parameters":  {"fill": "#D5A6E6", "stroke": "#8E44AD", "text": "#1A1A1A"},
    "consumables": {"fill": "#B5EAD7", "stroke": "#3D9970", "text": "#1A1A1A"},
    "environment": {"fill": "#B5EAD7", "stroke": "#3D9970", "text": "#1A1A1A"},
}

UO_CONTAINER_STYLES = {
    "hardware": {"fill": "#EBF2FA", "stroke": "#2C5F8A"},
    "software": {"fill": "#EBF8EB", "stroke": "#3D7A3D"},
}

COMPONENT_PREFIXES = {
    "input": "IN",
    "output": "OUT",
    "equipment": "EQUIP",
    "parameters": "PARAM",
    "consumables": "CONS",
    "environment": "ENV",
}

MAX_LABEL_LENGTH = 40
MAX_EDGE_LABEL_LENGTH = 30


def sanitize_mermaid_id(text: str) -> str:
    """Convert text to valid Mermaid node ID."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", text).strip("_")


def truncate_text(text: str, max_length: int = MAX_LABEL_LENGTH) -> str:
    """Truncate text with ellipsis if it exceeds max_length."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def sanitize_mermaid_label(text: str) -> str:
    """Escape characters that break Mermaid labels."""
    return text.replace('"', "'").replace("#", "No.").replace("&", "+")


def get_component_keys(uo_type: str) -> list:
    """Return the 4 visualization component keys for a UO type."""
    if uo_type == "software":
        return ["input", "output", "parameters", "environment"]
    return ["input", "output", "equipment", "consumables"]


def extract_component_label(component_data: dict, max_items: int = 2) -> str:
    """Extract a concise label from a component's items list.

    Takes up to max_items item names from component_data['items'].
    Returns empty string if no items found.
    """
    items = component_data.get("items", [])
    if not items:
        return ""
    names = [item.get("name", "") for item in items[:max_items] if item.get("name")]
    if not names:
        return ""
    label = ", ".join(names)
    if len(items) > max_items:
        label += f" +{len(items) - max_items}"
    return truncate_text(label)


def generate_mermaid_graph(variant_data: dict, workflow_id: str, variant_id: str) -> str:
    """
    Generate Mermaid diagram source for a workflow variant.

    Each UO is rendered as a subgraph containing up to 4 component nodes
    (Input, Output, Equipment/Parameters, Consumables/Environment) with
    consistent color coding. Inter-UO edges connect Output→Input nodes.

    Args:
        variant_data: variant composition dict containing uo_sequence and qc_checkpoints
        workflow_id: e.g., "WB030"
        variant_id: e.g., "V1"

    Returns:
        Mermaid source string
    """
    lines = [
        f"%% {workflow_id} {variant_id}: {variant_data.get('name', '')}",
        f"%% Enhanced UO component visualization",
        "graph TD",
    ]

    # Class definitions for component colors
    for comp_key, colors in COMPONENT_COLORS.items():
        cls_name = f"comp_{comp_key}"
        lines.append(
            f"    classDef {cls_name} fill:{colors['fill']},"
            f"stroke:{colors['stroke']},color:{colors['text']}"
        )
    # QC class
    lines.append(
        f"    classDef qc fill:{COLORS['qc_fill']},"
        f"stroke:{COLORS['qc_stroke']},color:{COLORS['text_color']}"
    )
    lines.append("")

    uo_sequence = variant_data.get("uo_sequence", [])

    # Track UO metadata for edge building
    uo_nodes = []  # list of {uo_id, sub_id, type, out_node, in_node, output_label}
    # Extract QC checkpoints from UO components (result.qc_checkpoint)
    # Key by (uo_id, index) to handle duplicate uo_ids
    uo_qc_map = {}  # (uo_id, index) → {qc_id, measurement, ...}
    qc_counter = 0
    for idx, uo in enumerate(uo_sequence):
        qc_data = uo.get("components", {}).get("result", {}).get("qc_checkpoint", None)
        if qc_data and isinstance(qc_data, dict) and qc_data.get("measurement"):
            qc_counter += 1
            if not qc_data.get("qc_id"):
                qc_data = dict(qc_data, qc_id=f"QC{qc_counter}")
            uo_qc_map[(uo.get("uo_id", ""), idx)] = qc_data

    # Build subgraph for each UO
    for i, uo in enumerate(uo_sequence):
        uo_id = uo.get("uo_id", f"UO{i}")
        instance_label = uo.get("instance_label", uo.get("uo_name", ""))
        uo_type = uo.get("type", "hardware")
        components = uo.get("components", {})
        comp_keys = get_component_keys(uo_type)
        sub_id = sanitize_mermaid_id(f"{uo_id}_{i}")

        # Check which components have data
        has_components = False
        for ck in comp_keys:
            comp_data = components.get(ck, {})
            if comp_data.get("items"):
                has_components = True
                break

        if not has_components:
            # Fallback: single node (legacy style)
            if uo_type == "software":
                cls = "comp_parameters"
                lines.append(f'    {sub_id}[/"{uo_id}: {sanitize_mermaid_label(instance_label)}"/]:::{cls}')
            else:
                cls = "comp_equipment"
                lines.append(f'    {sub_id}["{uo_id}: {sanitize_mermaid_label(instance_label)}"]:::{cls}')
            uo_nodes.append({
                "uo_id": uo_id, "sub_id": sub_id, "type": uo_type,
                "out_node": sub_id, "in_node": sub_id, "output_label": "",
            })
            lines.append("")
            continue

        # Subgraph with component nodes
        safe_label = sanitize_mermaid_label(instance_label)
        lines.append(f'    subgraph {sub_id}_sub ["{uo_id}: {safe_label}"]')

        out_node = None
        in_node = None
        output_label = ""

        for ck in comp_keys:
            comp_data = components.get(ck, {})
            label = extract_component_label(comp_data)
            if not label:
                continue

            prefix = COMPONENT_PREFIXES[ck]
            node_id = f"{sub_id}_{ck[:3]}"
            safe_comp_label = sanitize_mermaid_label(label)
            cls_name = f"comp_{ck}"
            lines.append(f'        {node_id}["{prefix}: {safe_comp_label}"]:::{cls_name}')

            if ck == "input":
                in_node = node_id
            elif ck == "output":
                out_node = node_id
                # Extract first output item name for edge labels
                items = comp_data.get("items", [])
                if items and items[0].get("name"):
                    output_label = truncate_text(items[0]["name"], MAX_EDGE_LABEL_LENGTH)

        lines.append("    end")

        # Apply container style
        container = UO_CONTAINER_STYLES.get(uo_type, UO_CONTAINER_STYLES["hardware"])
        lines.append(
            f"    style {sub_id}_sub fill:{container['fill']},"
            f"stroke:{container['stroke']},stroke-width:2px"
        )
        lines.append("")

        uo_nodes.append({
            "uo_id": uo_id,
            "sub_id": sub_id,
            "type": uo_type,
            "out_node": out_node or f"{sub_id}_sub",
            "in_node": in_node or f"{sub_id}_sub",
            "output_label": output_label,
        })

    # Build QC nodes (outside subgraphs, extracted from UO components)
    qc_node_by_index = {}  # uo_sequence index → {qc_id, node_id}
    for (uo_id, idx), qc_data in uo_qc_map.items():
        qc_id = qc_data["qc_id"]
        measurement = qc_data.get("measurement", "Quality Check")
        node_id = sanitize_mermaid_id(f"{qc_id}_{idx}")
        safe_meas = sanitize_mermaid_label(truncate_text(measurement, MAX_LABEL_LENGTH))
        lines.append(f'    {node_id}{{{{"{qc_id}: {safe_meas}"}}}}:::qc')
        qc_node_by_index[idx] = {
            "qc_id": qc_id,
            "node_id": node_id,
        }

    lines.append("")
    lines.append("    %% Inter-UO edges")

    # Build ordered node list (UO + QC interleaved)
    all_nodes = []
    for seq_idx, uo_info in enumerate(uo_nodes):
        all_nodes.append(uo_info)
        # Insert QC after this UO if it has a qc_checkpoint
        if seq_idx in qc_node_by_index:
            qc_info = qc_node_by_index[seq_idx]
            all_nodes.append({
                "type": "qc", "qc_id": qc_info["qc_id"],
                "node_id": qc_info["node_id"],
                "out_node": qc_info["node_id"],
                "in_node": qc_info["node_id"],
            })

    for i in range(len(all_nodes) - 1):
        from_node = all_nodes[i]
        to_node = all_nodes[i + 1]

        if from_node.get("type") == "qc":
            # QC pass → next UO input
            lines.append(f'    {from_node["node_id"]} -->|"Pass"| {to_node["in_node"]}')
            # QC fail → loop back to previous UO input
            if i >= 1:
                prev_uo = all_nodes[i - 1]
                lines.append(f'    {from_node["node_id"]} -.->|"Fail: re-check"| {prev_uo["in_node"]}')
        elif to_node.get("type") == "qc":
            # UO output → QC
            edge_label = sanitize_mermaid_label(from_node.get("output_label", ""))
            if edge_label:
                lines.append(f'    {from_node["out_node"]} -->|"{edge_label}"| {to_node["node_id"]}')
            else:
                lines.append(f'    {from_node["out_node"]} --> {to_node["node_id"]}')
        else:
            # UO output → next UO input
            from_id = from_node["out_node"]
            to_id = to_node["in_node"]
            edge_label = sanitize_mermaid_label(from_node.get("output_label", ""))

            is_data_flow = from_node.get("type") == "software" or to_node.get("type") == "software"
            if is_data_flow:
                if edge_label:
                    lines.append(f'    {from_id} -.->|"{edge_label}"| {to_id}')
                else:
                    lines.append(f'    {from_id} -.-> {to_id}')
            else:
                if edge_label:
                    lines.append(f'    {from_id} -->|"{edge_label}"| {to_id}')
                else:
                    lines.append(f'    {from_id} --> {to_id}')

    # Legend
    lines.append("")
    lines.append("    %% Legend")
    lines.append('    subgraph Legend ["Color Legend"]')
    lines.append('        L_in["Input"]:::comp_input')
    lines.append('        L_out["Output"]:::comp_output')
    lines.append('        L_eq["Equipment / Parameters"]:::comp_equipment')
    lines.append('        L_co["Consumables / Environment"]:::comp_consumables')
    lines.append('        L_qc{{"QC Checkpoint"}}:::qc')
    lines.append("    end")
    lines.append("    style Legend fill:#F9F9F9,stroke:#CCCCCC,stroke-width:1px")

    return "\n".join(lines)


def generate_variant_comparison(variants: list, workflow_id: str) -> str:
    """Generate a Mermaid diagram comparing multiple variants.

    Uses simplified single-node-per-UO view (not component subgraphs)
    for readability. Per-variant detail diagrams use the enhanced component view.
    """
    lines = [
        f"%% {workflow_id} Variant Comparison",
        "graph TD",
        f"    classDef hw fill:{COLORS['hw_fill']},stroke:{COLORS['hw_stroke']},color:{COLORS['text_color']}",
        f"    classDef sw fill:{COLORS['sw_fill']},stroke:{COLORS['sw_stroke']},color:{COLORS['text_color']}",
        f"    classDef qc fill:{COLORS['qc_fill']},stroke:{COLORS['qc_stroke']},color:{COLORS['text_color']}",
    ]

    # Add variant-specific class definitions
    for i, variant in enumerate(variants):
        color = VARIANT_COLORS[i % len(VARIANT_COLORS)]
        vid = variant.get("variant_id", f"V{i+1}")
        lines.append(f"    classDef {vid.lower()} fill:{color},stroke:#333,color:white")

    lines.append("")

    # Add nodes for each variant in subgraphs
    for i, variant in enumerate(variants):
        vid = variant.get("variant_id", f"V{i+1}")
        vname = variant.get("name", "")
        lines.append(f"    subgraph {vid}[\"{vid}: {vname}\"]")

        for j, uo in enumerate(variant.get("uo_sequence", [])):
            uo_id = uo.get("uo_id", f"UO{j}")
            label = uo.get("instance_label", uo.get("uo_name", ""))
            node_id = sanitize_mermaid_id(f"{vid}_{uo_id}_{j}")
            uo_type = uo.get("type", "hardware")
            cls = "sw" if uo_type == "software" else "hw"
            lines.append(f'        {node_id}["{uo_id}: {label}"]:::{cls}')

        lines.append("    end")
        lines.append("")

    return "\n".join(lines)


def generate_workflow_context_graph(wf_dir: str | Path, workflow_id: str) -> str:
    """
    Generate a Mermaid diagram showing upstream/downstream workflow connections.

    This diagram shows how the workflow fits into a broader biofoundry context
    by visualizing:
    - Upstream processes that feed into this workflow
    - Downstream processes that consume this workflow's outputs
    - The workflow itself as the central node

    Args:
        wf_dir: workflow output directory path
        workflow_id: e.g., "WB030"

    Returns:
        Mermaid source string
    """
    lines = [
        f"%% {workflow_id} Workflow Context Graph",
        f"%% Shows upstream and downstream process connections",
        "graph LR",
        "    classDef current fill:#F39C12,stroke:#D48A1A,color:white,stroke-width:3px",
        "    classDef upstream fill:#3498DB,stroke:#2C5F8A,color:white",
        "    classDef downstream fill:#2ECC71,stroke:#229954,color:white",
        "",
    ]

    # Load workflow data to extract input/output context
    workflow_dir = Path(wf_dir) / "04_workflow"
    variant_files = sorted(workflow_dir.glob("variant_V*.json"))

    if not variant_files:
        lines.append(f'    WF["{workflow_id}"]:::current')
        return "\n".join(lines)

    # Collect all inputs and outputs across variants
    all_inputs = set()
    all_outputs = set()

    for vf in variant_files:
        with open(vf, "r", encoding="utf-8") as f:
            variant_data = json.load(f)

        for uo in variant_data.get("uo_sequence", []):
            components = uo.get("components", {})

            # Collect inputs
            input_comp = components.get("input", {})
            for item in input_comp.get("items", []):
                if item.get("name"):
                    all_inputs.add(item["name"])

            # Collect outputs
            output_comp = components.get("output", {})
            for item in output_comp.get("items", []):
                if item.get("name"):
                    all_outputs.add(item["name"])

    # Create upstream nodes (inputs that are likely from other processes)
    upstream_nodes = []
    for i, inp in enumerate(sorted(all_inputs)[:5]):  # Limit to 5 for readability
        node_id = f"UP{i+1}"
        safe_label = sanitize_mermaid_label(truncate_text(inp, 30))
        lines.append(f'    {node_id}["{safe_label}"]:::upstream')
        upstream_nodes.append(node_id)

    # Central workflow node
    lines.append(f'    WF["{workflow_id}"]:::current')

    # Create downstream nodes (outputs that feed other processes)
    downstream_nodes = []
    for i, out in enumerate(sorted(all_outputs)[:5]):  # Limit to 5 for readability
        node_id = f"DN{i+1}"
        safe_label = sanitize_mermaid_label(truncate_text(out, 30))
        lines.append(f'    {node_id}["{safe_label}"]:::downstream')
        downstream_nodes.append(node_id)

    lines.append("")
    lines.append("    %% Connections")

    # Upstream → Workflow
    for node_id in upstream_nodes:
        lines.append(f"    {node_id} --> WF")

    # Workflow → Downstream
    for node_id in downstream_nodes:
        lines.append(f"    WF --> {node_id}")

    return "\n".join(lines)


def save_mermaid(content: str, output_path: str | Path):
    """Save Mermaid source to .mmd file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def generate_all_visualizations(wf_dir: str | Path, workflow_id: str) -> dict:
    """
    Generate all Mermaid visualizations for a workflow.

    Reads variant compositions from 04_workflow/ and generates:
    - Per-variant Mermaid graph files
    - Variant comparison Mermaid
    - Workflow context graph Mermaid

    Returns summary of generated files.
    """
    wf_dir = Path(wf_dir)
    viz_dir = wf_dir / "05_visualization"
    viz_dir.mkdir(parents=True, exist_ok=True)
    workflow_dir = wf_dir / "04_workflow"

    generated = []

    print("Loading variant data...")
    # Load variant files
    variant_files = sorted(workflow_dir.glob("variant_V*.json"))
    variants = []

    for vf in variant_files:
        with open(vf, "r", encoding="utf-8") as f:
            variant_data = json.load(f)

        vid = variant_data.get("variant_id", vf.stem.split("_")[1])

        print(f"Generating Mermaid graph for {vid}...")
        # Generate Mermaid
        mmd_content = generate_mermaid_graph(variant_data, workflow_id, vid)
        mmd_path = save_mermaid(mmd_content, viz_dir / f"workflow_graph_{vid}.mmd")
        generated.append(str(mmd_path))

        variants.append(variant_data)

    # Generate variant comparison
    if len(variants) > 1:
        print("Generating variant comparison...")
        comparison_mmd = generate_variant_comparison(variants, workflow_id)
        comp_path = save_mermaid(comparison_mmd, viz_dir / "variant_comparison.mmd")
        generated.append(str(comp_path))

    # Generate workflow context graph
    print("Generating workflow context graph...")
    context_mmd = generate_workflow_context_graph(wf_dir, workflow_id)
    context_path = save_mermaid(context_mmd, viz_dir / "workflow_context.mmd")
    generated.append(str(context_path))

    print(f"Generated {len(generated)} Mermaid files")
    return {
        "generated": datetime.now().isoformat(),
        "output_directory": str(viz_dir),
        "files": generated,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python visualize_workflow.py <workflow_output_dir> <workflow_id>")
        sys.exit(1)

    result = generate_all_visualizations(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2, ensure_ascii=False))
