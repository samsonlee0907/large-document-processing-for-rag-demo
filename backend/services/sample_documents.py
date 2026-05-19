from __future__ import annotations

import math
import random
import textwrap
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from backend.core.config import settings

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional dependency
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
except Exception:  # pragma: no cover - optional dependency
    canvas = None  # type: ignore[assignment]
    ImageReader = None  # type: ignore[assignment]
    letter = (612, 792)


@dataclass(slots=True)
class GeneratedSample:
    path: Path
    page_count: int
    file_name: str
    section_interval: int
    topic_key: str | None = None
    report_title: str | None = None


@dataclass(slots=True)
class ResearchSection:
    title: str
    thesis: str
    signals: list[str]
    implications: list[str]
    watch_items: list[str]
    diagram_style: str
    diagram_caption: str
    references: list[str]


@dataclass(slots=True)
class ResearchReportBlueprint:
    topic_key: str
    file_stem: str
    report_title: str
    report_subtitle: str
    sections: list[ResearchSection]


GENERATIVE_AI_FUTURES_SECTIONS: list[ResearchSection] = [
    ResearchSection(
        title="Capability Frontier",
        thesis=(
            "Generative AI capability is still accelerating, with frontier systems improving on coding, "
            "science reasoning, multimodal understanding, and computer-use tasks."
        ),
        signals=[
            "Frontier-model development is now dominated by industry, and benchmark gains continue to arrive in sharp jumps rather than smooth increments.",
            "Coding systems are becoming strong enough to alter software delivery economics even before they are fully reliable on open-ended production tasks.",
            "Multimodal systems are expanding the usable interface for enterprise knowledge because the same model family can reason over text, images, and workflows.",
            "Agent benchmarks show real progress, but task completion is still uneven enough that orchestration and verification remain first-class design concerns.",
        ],
        implications=[
            "Enterprises should expect more capability volatility between model generations and design evaluation loops that can absorb rapid upgrades.",
            "Document-centric applications should preserve provenance and structured context because stronger models exploit richer retrieval signals rather than raw text alone.",
            "Operational teams need model qualification gates, not one-time bakeoffs, because the capability curve is moving faster than annual architecture cycles.",
        ],
        watch_items=[
            "Watch for jumps in task generality rather than isolated benchmark wins.",
            "Track whether model improvements translate into lower review load per business workflow.",
            "Plan for a mixed estate of local, specialist, and frontier models rather than one universal model choice.",
        ],
        diagram_style="curve",
        diagram_caption="A stylized capability curve showing coding, reasoning, and agent performance rising at different speeds.",
        references=[
            "Stanford HAI AI Index 2026",
            "Stanford HAI Technical Performance 2026",
        ],
    ),
    ResearchSection(
        title="Adoption And Consumer Value",
        thesis=(
            "Generative AI has moved from experimentation to mainstream use unusually quickly, but depth of adoption still varies by sector, geography, and workflow maturity."
        ),
        signals=[
            "Population-level adoption is occurring faster than prior computing waves, while organizational adoption is high but unevenly translated into workflow redesign.",
            "Many firms now use generative AI in at least one business function, yet agent deployment remains much earlier than basic assistant usage.",
            "Consumer value is rising even where direct monetization remains limited, signaling strong demand for low-friction AI experiences.",
            "Country-level adoption correlates with income, connectivity, and policy support, creating a diffusion map that is not identical to model-development leadership.",
        ],
        implications=[
            "The near-term differentiator is not basic access to generative AI but the ability to embed it into repeatable knowledge, service, and decision workflows.",
            "Enterprise leaders should distinguish breadth of use from depth of transformation; many deployments are wide but still shallow.",
            "Change management and interface design matter as much as model quality once adoption passes the pilot phase.",
        ],
        watch_items=[
            "Measure adoption by workflow completion quality, not only active users.",
            "Expect the next wave of value to come from integration with line-of-business systems.",
            "Use retrieval analytics to identify which documents actually create grounded value after rollout.",
        ],
        diagram_style="bar",
        diagram_caption="A diffusion chart illustrating the gap between broad access, repeated use, and fully redesigned workflows.",
        references=[
            "Stanford HAI AI Index 2026 Economy",
            "OECD Productivity And Innovation Review 2025",
        ],
    ),
    ResearchSection(
        title="Workforce Transformation",
        thesis=(
            "The dominant near-term labor effect is job transformation rather than pure automation, with exposure concentrated in clerical and strongly digitized work."
        ),
        signals=[
            "High-exposure roles are not evenly distributed; clerical occupations remain most exposed while professional work is seeing deeper task-level augmentation.",
            "The youngest workers in exposed pipelines may feel the earliest labor-market effects because entry-level tasks are easier to absorb into AI-assisted processes.",
            "Gender and income-level differences matter because occupational structure shapes who is exposed and how transition support should be targeted.",
            "Task decomposition is a better planning unit than job titles when estimating how generative AI changes work.",
        ],
        implications=[
            "Reskilling should focus on review, exception handling, customer judgment, and process control instead of generic 'AI literacy' alone.",
            "Knowledge platforms should preserve auditability because workers increasingly operate as supervisors of AI-generated drafts and retrieval outputs.",
            "Managers need redesign playbooks that describe what humans own after generative AI takes the first draft or first pass.",
        ],
        watch_items=[
            "Track how entry-level knowledge work changes in hiring, onboarding, and promotion ladders.",
            "Plan for new reviewer and evaluator roles even if headcount totals stay stable.",
            "Use grounded document workflows as training surfaces for human-AI collaboration.",
        ],
        diagram_style="ladder",
        diagram_caption="A task-exposure ladder showing movement from low exposure to supervised transformation and high exposure work redesign.",
        references=[
            "ILO Working Paper 140 (2025)",
            "ILO Generative AI And Jobs 2025 Update",
        ],
    ),
    ResearchSection(
        title="Productivity And Innovation Systems",
        thesis=(
            "Generative AI appears to have the characteristics of a general-purpose technology, but long-run productivity gains depend on complementary process and policy change."
        ),
        signals=[
            "Experimental studies show meaningful productivity gains in some tasks, especially where drafting, synthesis, or ideation can be accelerated.",
            "Benefits vary by user skill and task design, which means unmanaged rollouts can amplify inconsistency instead of performance.",
            "Innovation gains may emerge through faster iteration cycles, lower experimentation costs, and wider participation in technical work.",
            "Long-term productivity effects are likely to lag adoption because organizations must redesign surrounding processes before gains compound.",
        ],
        implications=[
            "The biggest returns may come from re-architected workflows, not from simply dropping a model into a legacy process.",
            "Document pipelines become productivity systems when they reduce search time, improve answer trust, and shorten review loops.",
            "Leaders should invest in measurement, not hype, so they can identify where human-AI collaboration actually changes cost or throughput.",
        ],
        watch_items=[
            "Look for innovation-spawning effects in research, engineering, and service design.",
            "Measure throughput, accuracy, and rework together because productivity gains can hide quality losses.",
            "Treat generative AI as a platform capability that requires organizational complements.",
        ],
        diagram_style="flywheel",
        diagram_caption="A productivity flywheel linking better tools, faster experiments, redesigned workflows, and cumulative business value.",
        references=[
            "OECD GPT Working Paper 2025",
            "OECD Productivity And Innovation Review 2025",
        ],
    ),
    ResearchSection(
        title="Enterprise Agents And Operations",
        thesis=(
            "Agentic systems are improving quickly, but most enterprises are still earlier in operational maturity than the benchmark headlines imply."
        ),
        signals=[
            "Benchmarks show large gains in agent task success, yet real-world enterprise workflows remain brittle because tools, permissions, and exception paths are messy.",
            "Most organizations still deploy assistants more often than fully delegated agents across business functions.",
            "Grounded retrieval, policy constraints, and human approval remain the practical control points that make agent deployments acceptable in enterprise settings.",
            "Reliability depends on decomposition, memory, and evaluation infrastructure as much as the frontier model itself.",
        ],
        implications=[
            "Agent programs should start with bounded tasks and visible checkpoints rather than hidden autonomy.",
            "Knowledge bases need clean chunking and metadata because agentic retrieval quality degrades when the corpus is flattened into generic text.",
            "Observability is mandatory; without traces and citations, agent operations become impossible to debug at scale.",
        ],
        watch_items=[
            "Measure agent success on workflow completion, tool correctness, and escalation quality.",
            "Expect stronger need for routing policies between local search, retrieval, and model reasoning.",
            "Preserve human override for high-impact workflow branches.",
        ],
        diagram_style="loop",
        diagram_caption="A supervised agent loop connecting user intent, retrieval, tool use, human approval, and audited action.",
        references=[
            "Stanford HAI AI Index 2026",
            "Stanford HAI Technical Performance 2026",
        ],
    ),
    ResearchSection(
        title="Data Rights, Trust, And Governance",
        thesis=(
            "The future of generative AI will be shaped as much by governance and data access as by model scale, because trust failures and rights conflicts can slow deployment."
        ),
        signals=[
            "Responsible-AI measurement remains uneven, and gains in one risk dimension can come at the cost of another.",
            "Web data access is becoming more restricted, increasing pressure on licensed, private, and synthetic data strategies.",
            "Organizations need practical controls for safety, privacy, transparency, and misuse that can operate at system level rather than policy-document level.",
            "Governance is moving from abstract principle statements toward operational requirements, testing, and evidence collection.",
        ],
        implications=[
            "Document systems should preserve source lineage, retention rules, and access boundaries because these are governance features, not optional metadata extras.",
            "Risk management frameworks are most useful when they map directly to product checkpoints, evaluation suites, and release criteria.",
            "Trustworthy AI programs need tradeoff management because fairness, privacy, openness, and accuracy are not always optimized together.",
        ],
        watch_items=[
            "Track how data licensing and usage controls alter training and retrieval economics.",
            "Maintain audit-ready evidence for model, prompt, and corpus changes.",
            "Use grounded citations as a trust surface for both users and compliance teams.",
        ],
        diagram_style="balance",
        diagram_caption="A governance balance diagram showing tradeoffs among safety, privacy, transparency, and performance.",
        references=[
            "NIST AI 600-1",
            "Stanford HAI Responsible AI 2026",
        ],
    ),
    ResearchSection(
        title="Infrastructure, Chips, And Energy",
        thesis=(
            "The next phase of generative AI is constrained by compute, energy, and supply-chain concentration, not just algorithmic ambition."
        ),
        signals=[
            "Data-center electricity demand linked to AI is projected to rise sharply through 2030, even as efficiency improves.",
            "Renewables are expected to supply much of the incremental demand growth, but fossil generation remains a meaningful near-term bridge in many regions.",
            "AI hardware remains concentrated in a narrow supply chain, creating resilience and sovereignty concerns.",
            "Infrastructure spending is now a strategic differentiator for model builders, clouds, and governments.",
        ],
        implications=[
            "Enterprise AI strategy needs cost discipline, not only capability ambition, because compute and energy economics increasingly shape architecture choices.",
            "Retrieval quality improvements can be economically powerful because they reduce wasted reasoning cycles and unnecessary model calls.",
            "System design should account for latency, capacity, and environmental constraints alongside model accuracy.",
        ],
        watch_items=[
            "Watch for new optimization layers: smaller expert models, distillation, caching, and retrieval-first answers.",
            "Expect energy and grid constraints to influence where future AI clusters can scale.",
            "Treat infrastructure resilience as part of AI risk management.",
        ],
        diagram_style="stack",
        diagram_caption="An infrastructure stack showing chips, data centers, power supply, and optimization layers feeding enterprise AI workloads.",
        references=[
            "IEA Energy And AI 2025",
            "Stanford HAI AI Index 2026",
        ],
    ),
    ResearchSection(
        title="Sovereignty And Geopolitical Competition",
        thesis=(
            "Generative AI is increasingly a sovereignty project as countries pursue control over compute, data, talent, and model ecosystems."
        ),
        signals=[
            "The U.S.-China frontier-model performance gap has narrowed materially even while capability ecosystems remain differently structured.",
            "Governments are expanding AI strategies, public investment, and sovereign compute initiatives.",
            "Data localization and domestic-capacity policies are shaping how AI systems are built and where knowledge can flow.",
            "Geopolitical competition now involves standards, chips, cloud regions, open-weight ecosystems, and procurement policy.",
        ],
        implications=[
            "Cross-border knowledge systems must be designed with location, compliance, and access boundaries in mind from the start.",
            "Enterprises should expect regional variation in hosting, model availability, and acceptable governance patterns.",
            "AI architecture choices increasingly intersect with procurement, security, and jurisdiction strategy.",
        ],
        watch_items=[
            "Monitor regional compute capacity, not only model releases.",
            "Track how sovereign-AI policy affects ecosystem openness and interconnection.",
            "Plan for multi-region knowledge operations where one global design is no longer sufficient.",
        ],
        diagram_style="matrix",
        diagram_caption="A sovereignty matrix mapping infrastructure, data, models, applications, and talent across regions.",
        references=[
            "Stanford HAI Policy And Governance 2026",
            "Stanford HAI AI Index 2026",
        ],
    ),
    ResearchSection(
        title="Industry Structure And Business Models",
        thesis=(
            "Generative AI is reshaping industry structure through rapid funding, heavy capex, lower entry barriers for some firms, and new control points for platforms."
        ),
        signals=[
            "Corporate investment and startup funding accelerated sharply, but costs also rose as model builders and hyperscalers expanded infrastructure.",
            "Some value is shifting toward workflow ownership, integration, and proprietary data rather than model access alone.",
            "Open and closed ecosystems are both influencing competition, with differentiation increasingly tied to execution and distribution.",
            "Vertical copilots and domain agents may capture more durable value than generic interfaces once integration work is complete.",
        ],
        implications=[
            "Business-model resilience depends on whether an offering owns a workflow, a user community, or a data advantage.",
            "Knowledge products should be designed as reusable enterprise assets that support search, chat, automation, and audit functions simultaneously.",
            "RAG quality becomes a margin lever when it reduces unnecessary model usage and improves task completion on first response.",
        ],
        watch_items=[
            "Track whether value pools move toward orchestration, compliance, or domain packaging.",
            "Measure recurring value, not launch-day attention.",
            "Watch capital intensity as carefully as feature breadth.",
        ],
        diagram_style="chain",
        diagram_caption="A business-model chain highlighting where value can accumulate: models, platforms, data, workflow integration, and distribution.",
        references=[
            "Stanford HAI Economy 2026",
            "OECD Productivity And Innovation Review 2025",
        ],
    ),
    ResearchSection(
        title="Scenarios For 2027 To 2030",
        thesis=(
            "The most plausible future is not a single straight line but a range of scenarios shaped by capability gains, trust, energy, and institutional readiness."
        ),
        signals=[
            "One path features strong capability growth matched by governance, grid expansion, and workflow redesign.",
            "Another path features widespread deployment but fragmented governance, uneven trust, and rising friction around data and energy.",
            "A more constrained path emerges if compute bottlenecks, public backlash, or regulatory confusion slow deployment into the highest-value workflows.",
            "Scenario planning matters because organizations are moving from experimentation to AI-dependent operations.",
        ],
        implications=[
            "Enterprise roadmaps should include trigger points that decide when to scale, regionalize, or slow a deployment program.",
            "Knowledge ingestion quality remains valuable in every scenario because grounded systems age more gracefully than purely prompt-driven ones.",
            "The best preparation is a portfolio approach: strong retrieval, flexible orchestration, measurable governance, and optional model backends.",
        ],
        watch_items=[
            "Define leading indicators for trust, cost, latency, and policy change.",
            "Use documents, diagrams, and citations as evidence surfaces in scenario review exercises.",
            "Revisit scenarios quarterly because the capability frontier is moving faster than traditional planning cadences.",
        ],
        diagram_style="quadrant",
        diagram_caption="A scenario matrix spanning capability acceleration against governance and infrastructure readiness.",
        references=[
            "Stanford HAI AI Index 2026",
            "IEA Energy And AI 2025",
            "NIST AI 600-1",
        ],
    ),
]


CONSTRUCTION_INDUSTRY_SECTIONS: list[ResearchSection] = [
    ResearchSection(
        title="Demand, Infrastructure, And Delivery Pressure",
        thesis=(
            "Construction demand is being reshaped by infrastructure renewal, resilient retrofits, housing pressure, and "
            "data-center buildout, which together create a more complex pipeline than a single-cycle market story."
        ),
        signals=[
            "Public and private capital are both flowing into long-duration projects, but project execution remains uneven because approval cycles, supply constraints, and financing conditions vary by region.",
            "Construction demand now includes more resilience, energy, and digital-infrastructure work, which changes the mix of trades, materials, and lifecycle requirements across portfolios.",
            "The market is no longer defined by one dominant project type; building owners and contractors increasingly balance new build, retrofit, and infrastructure modernization at the same time.",
            "Project teams need stronger document control because permitting packs, design revisions, contracts, and field records move faster than manual coordination can safely absorb.",
        ],
        implications=[
            "Knowledge systems for construction should treat projects as living evidence sets with changing drawings, specifications, submittals, RFIs, and field reports.",
            "Retrieval quality improves when chunks preserve package boundaries such as bid form, design narrative, schedule note, and commissioning requirement instead of flattening everything into one text stream.",
            "Large-program oversight depends on being able to compare many active documents across time rather than asking one-off questions against isolated PDFs.",
        ],
        watch_items=[
            "Track whether retrofit and resilience work rises faster than pure new-build activity in the target portfolio.",
            "Monitor which project classes create the highest document volume and coordination overhead.",
            "Use ingestion telemetry to measure where review bottlenecks shift from design to procurement and field execution.",
        ],
        diagram_style="bar",
        diagram_caption="A demand-mix chart showing concurrent pressure from infrastructure, housing, retrofit, and digital-infrastructure projects.",
        references=[
            "GlobalABC Global Status Report for Buildings and Construction 2024/2025",
            "World Bank Better Buildings for a Changing World 2026",
            "U.S. Census New Residential Construction Press Release 2026",
        ],
    ),
    ResearchSection(
        title="Labor, Skills, And Safety",
        thesis=(
            "Labor scarcity and safety exposure remain central constraints in construction, so productivity gains depend as much on workforce design and hazard reduction as on software."
        ),
        signals=[
            "Construction remains a major employment engine, but labor conditions and skills availability vary widely across geographies and trades.",
            "Safety risk remains structurally high because field work still concentrates fall, equipment, electrical, dust, and site-movement hazards.",
            "Digital tools only create value when they reduce uncertainty for supervisors, crews, and subcontractors instead of adding another reporting burden.",
            "Training and information flow are operational controls in construction, not soft side topics, because errors propagate quickly from drawings to site execution.",
        ],
        implications=[
            "Document pipelines should surface safety-critical procedures, method statements, and hazard controls as first-class retrievable artifacts.",
            "Construction copilots need role-aware grounding so a superintendent, estimator, and safety lead do not all receive the same answer from the same evidence set.",
            "Image evidence, annotated figures, and page-anchored citations are particularly important in safety and field workflow questions.",
        ],
        watch_items=[
            "Track the retrieval demand for SOPs, toolbox talks, inspection records, and incident-prevention content.",
            "Measure whether crews spend less time searching for the right revision or safety instruction after rollout.",
            "Watch where multimodal evidence is needed because pure text answers are insufficient for field execution.",
        ],
        diagram_style="ladder",
        diagram_caption="A workforce ladder showing the climb from labor availability to training quality, safe execution, and repeatable productivity.",
        references=[
            "International Labour Organization Construction Sector Overview",
            "ILO Safety and Health in Construction",
            "OSHA Construction Industry",
        ],
    ),
    ResearchSection(
        title="Decarbonization, Energy, And Embodied Carbon",
        thesis=(
            "The future of construction is inseparable from decarbonization because building operations, materials, energy codes, and embodied carbon now shape both project scope and financing."
        ),
        signals=[
            "Global building and construction strategies increasingly combine operational efficiency, electrification, renewable integration, and material choices rather than treating them as separate workstreams.",
            "Embodied carbon has become a practical design and procurement topic because material selection and product transparency affect project-level emissions decisions earlier in the lifecycle.",
            "Sustainable building strategy now depends on better data management, financing, and supply-chain visibility, not only on green-design intent.",
            "Owners are under pressure to connect design commitments to measurable delivery outcomes, which elevates traceable documentation and evidence capture.",
        ],
        implications=[
            "Low-carbon construction programs need retrieval systems that can link specifications, EPDs, submittals, commissioning records, and change events.",
            "Section-aware chunking is important because carbon and energy requirements are often scattered across addenda, schedules, product sheets, and compliance appendices.",
            "Construction knowledge bases should preserve document lineage so teams can explain which revision supported a sustainability claim or procurement decision.",
        ],
        watch_items=[
            "Track how often project teams query embodied-carbon evidence versus energy-code evidence.",
            "Watch whether document graphs need product-to-package links across procurement and compliance reviews.",
            "Preserve tables and schedules intact where carbon factors or performance thresholds are listed.",
        ],
        diagram_style="balance",
        diagram_caption="A sustainability balance showing the tradeoffs among operational energy, embodied carbon, compliance, and cost.",
        references=[
            "GlobalABC Global Status Report for Buildings and Construction 2024/2025",
            "World Green Building Council Embodied Carbon",
            "World Economic Forum Green Building Revolution 2024",
        ],
    ),
    ResearchSection(
        title="Industrialized Construction And Prefabrication",
        thesis=(
            "Industrialized construction, prefabrication, and kit-of-parts delivery remain important levers for schedule certainty and waste reduction, but they require earlier coordination discipline."
        ),
        signals=[
            "Offsite and modular approaches shift risk left, forcing design freeze decisions, procurement visibility, and logistics precision earlier than many traditional teams expect.",
            "Industrialized delivery increases the value of structured product and package data because late ambiguity is more expensive once manufacturing and shipment have started.",
            "The business case improves when repeatable document templates, controlled revisions, and package-level retrieval reduce coordination waste.",
            "Prefabrication is as much an information-management challenge as a fabrication challenge because field success depends on clean handoffs between design, supplier, and site teams.",
        ],
        implications=[
            "Construction RAG corpora should preserve package, assembly, and trade boundaries so users can ask questions about one subsystem without retrieving unrelated site information.",
            "Chunking should avoid splitting fabrication tables, bills of materials, or installation steps in ways that destroy assembly coherence.",
            "Figure extraction is useful for modular workflows because diagrams, exploded views, and layout details often carry more operational meaning than narrative text alone.",
        ],
        watch_items=[
            "Measure how often users ask package-level questions instead of whole-project questions.",
            "Track whether structured tables and figure evidence are retrieved together for installation and coordination queries.",
            "Watch where revision-control metadata becomes the deciding factor in answer trust.",
        ],
        diagram_style="flywheel",
        diagram_caption="An industrialized-delivery flywheel linking design standardization, factory throughput, logistics readiness, and field productivity.",
        references=[
            "World Economic Forum Shaping the Future of Construction",
            "Autodesk 2025 State of Design & Make: Spotlight on Construction",
        ],
    ),
    ResearchSection(
        title="BIM, Digital Twins, And Lifecycle Data",
        thesis=(
            "BIM and digital twins are converging into a lifecycle data plane for construction and operations, but the value depends on whether teams can connect model context to trustworthy project evidence."
        ),
        signals=[
            "Built-environment practitioners increasingly treat BIM and digital twins as complementary rather than competing constructs.",
            "Lifecycle value grows when project information can flow from planning and design into construction, commissioning, and operations without losing meaning.",
            "Digital-twin adoption raises the bar for structured metadata because geometry alone does not answer questions about obligations, approvals, maintenance, or risk.",
            "Construction teams need a bridge between model context and document evidence so field questions can be answered with both spatial and contractual grounding.",
        ],
        implications=[
            "Intermediate document models should preserve section hierarchy, page anchors, and source identifiers so knowledge can later be connected to BIM elements or twin objects.",
            "A construction corpus becomes more useful when drawings, narratives, photos, and submittal records can all be retrieved as one evidence package.",
            "Image understanding matters because many built-environment questions reference diagrams, plans, elevations, and detail callouts instead of prose alone.",
        ],
        watch_items=[
            "Track where teams want element-level retrieval versus package-level retrieval.",
            "Measure how often figure evidence is decisive in design, coordination, or operations answers.",
            "Plan for metadata schemas that can later attach chunks to asset IDs, spaces, systems, or trades.",
        ],
        diagram_style="blueprint_building",
        diagram_caption="A CAD-style blueprint sheet showing a building floor plan, grid lines, room zones, and lifecycle callouts for BIM and digital twin context.",
        references=[
            "NIBS Digital Twins for the Built Environment",
            "NIBS BIM and Digital Twins Coexist to Drive Sustainability",
        ],
    ),
    ResearchSection(
        title="Construction Knowledge Architecture",
        thesis=(
            "Construction AI works best when drawings, RFIs, submittals, schedules, permits, photos, and safety records feed one governed retrieval architecture instead of many disconnected document silos."
        ),
        signals=[
            "Construction programs accumulate mixed media across design, procurement, field execution, and turnover, which means retrieval systems must handle text, tables, images, and revision history together.",
            "Knowledge quality depends on document breakdown, metadata enrichment, and source lineage because the same question often spans specifications, plans, and field records.",
            "Agentic retrieval is especially useful in construction when a question needs to decompose across contract scope, design intent, and current site evidence.",
            "Architecture decisions around storage, parsing, chunking, and evidence serving directly affect whether the answer can reference the right drawing, figure, or section page.",
        ],
        implications=[
            "The ingestion pipeline should split large packages, extract figures, normalize structure, preserve breadcrumbs, and publish retrieval-ready chunks instead of raw blobs.",
            "Search-oriented architecture diagrams are valuable because stakeholders need to understand how BIM, document intelligence, storage, and grounded chat fit together.",
            "Construction assistants should return both textual citations and visual evidence when plans, markups, or diagrams are relevant to the answer.",
        ],
        watch_items=[
            "Track whether the most common questions span multiple source types and therefore benefit from explicit subquery planning.",
            "Measure the hit rate of figure evidence in grounded answers for coordination-style prompts.",
            "Keep the parser, chunker, and index adapters swappable because project content maturity varies widely across owners and contractors.",
        ],
        diagram_style="blueprint_architecture",
        diagram_caption="A CAD-style architecture sheet for construction knowledge: project sources flow through parsing and chunking into search, agentic retrieval, and grounded assistant answers.",
        references=[
            "Azure AI Search Agentic Retrieval",
            "NIBS Digital Twins for the Built Environment",
            "Autodesk Construction AI Resources",
        ],
    ),
    ResearchSection(
        title="AI, Automation, And Field Productivity",
        thesis=(
            "AI in construction will create durable value where it automates coordination overhead, protects data integrity, and shortens decision cycles without obscuring accountability."
        ),
        signals=[
            "Construction leaders are evaluating AI alongside sustainability and productivity rather than as a standalone experiment.",
            "Trusted AI in construction depends on secure project data, revision awareness, and explainable outputs because commercial and safety risk are high.",
            "Field productivity gains come from removing document friction, surfacing the right evidence faster, and reducing rework caused by stale information.",
            "Multimodal models expand the feasible interface for construction because teams ask questions against photos, diagrams, punch lists, and narrative documents in the same workflow.",
        ],
        implications=[
            "Grounded construction chat should separate retrieval from synthesis so the system can cite the specific package, page, and figure that drove the answer.",
            "GPT-based image understanding is useful for figure-heavy packages, but it should enrich evidence rather than replace the original project artifact.",
            "The most practical early wins are usually in project controls, design coordination, turnover, and field information access.",
        ],
        watch_items=[
            "Track whether AI questions are shifting from generic summaries to operational coordination prompts.",
            "Measure time saved in finding the current answer rather than only message volume.",
            "Watch where answer quality depends on diagram extraction, table preservation, or page-level grounding.",
        ],
        diagram_style="loop",
        diagram_caption="A field-productivity loop connecting question intake, grounded retrieval, supervisor review, and auditable project action.",
        references=[
            "Autodesk 2025 State of Design & Make: Spotlight on Construction",
            "Autodesk Trust and AI in Construction Resources",
        ],
    ),
    ResearchSection(
        title="Procurement, Supply Chain, And Cost Control",
        thesis=(
            "Construction cost control is increasingly an information problem because procurement risk, substitution requests, logistics, and revisions must be resolved against shared evidence."
        ),
        signals=[
            "Material and equipment choices now sit inside a tighter web of cost, carbon, availability, and compliance tradeoffs.",
            "Supply-chain decisions often require reading across specifications, approved equals, lead-time notes, vendor documents, and change records.",
            "Procurement teams need better retrieval not only for speed but to reduce commercial risk from missed conditions or stale revisions.",
            "The highest-value answers often combine narrative scope, structured tables, and historical approval evidence in one response.",
        ],
        implications=[
            "Chunk records should carry package identifiers, timestamps, checksums, and source URIs where available so deduplication and incremental indexing remain reliable.",
            "Construction knowledge bases should preserve table-heavy procurement content because pricing, alternates, and compliance often live in tabular form.",
            "Retrieval systems should support incremental re-indexing so late addenda and vendor updates do not require full corpus rebuilds.",
        ],
        watch_items=[
            "Measure how frequently procurement answers require more than one source package.",
            "Track where incremental indexing changes the freshness of commercial answers.",
            "Watch whether package metadata or figure evidence becomes the dominant relevance signal.",
        ],
        diagram_style="chain",
        diagram_caption="A procurement chain linking specifications, approved products, logistics, change control, and cost visibility.",
        references=[
            "GlobalABC Global Status Report for Buildings and Construction 2024/2025",
            "World Bank Better Buildings for a Changing World 2026",
        ],
    ),
    ResearchSection(
        title="Resilience, Retrofit, And Climate Adaptation",
        thesis=(
            "Climate adaptation is pushing construction beyond new-build logic toward resilient retrofit, recovery, and long-horizon asset strengthening."
        ),
        signals=[
            "Resilient buildings contribute to service continuity, risk reduction, and long-term competitiveness rather than only to post-disaster repair.",
            "Adaptation programs create complex evidence chains because resilience planning spans codes, condition studies, design options, funding rules, and maintenance requirements.",
            "The same project portfolio may combine repair, upgrade, electrification, and hazard-reduction objectives, which raises information complexity.",
            "Construction intelligence systems need to support both emergency-response retrieval and slow-cycle capital planning evidence.",
        ],
        implications=[
            "Retrieval systems for retrofit programs should preserve historical context so users can compare prior conditions, new interventions, and compliance evidence.",
            "Large resilience programs benefit from structure-aware chunking because the same asset may have many phases, packages, and funding conditions.",
            "Image and figure evidence are useful when answering questions about site condition, hazard zones, and phased work plans.",
        ],
        watch_items=[
            "Track how often queries reference phased retrofit work versus whole-project scope.",
            "Measure whether climate-risk questions need cross-document reasoning more often than standard design questions.",
            "Preserve evidence packages that combine tables, diagrams, and narrative scope together.",
        ],
        diagram_style="stack",
        diagram_caption="A resilience stack showing hazard context, design intervention, financing, construction delivery, and operational continuity.",
        references=[
            "World Bank Better Buildings for a Changing World 2026",
            "World Bank Building Climate Resilience Into the Construction Industry",
        ],
    ),
    ResearchSection(
        title="Scenarios For 2027 To 2030",
        thesis=(
            "The most likely future for construction is a mixed scenario: tighter labor and carbon constraints, better digital coordination, more retrofit work, and selective AI scale-up where evidence quality is high."
        ),
        signals=[
            "One scenario accelerates because digital workflows, low-carbon procurement, and resilient capital programs mature together.",
            "Another scenario stalls because fragmented data, weak interoperability, and skills shortages slow execution even when funding exists.",
            "A third scenario favors organizations that master information flow, because they can absorb AI, prefabrication, and lifecycle data faster than peers.",
            "Across scenarios, the common differentiator is the ability to connect trustworthy evidence to real project decisions.",
        ],
        implications=[
            "Construction firms should treat document ingestion quality as part of operating strategy, not just as an IT convenience layer.",
            "Grounded assistants will matter most where they reduce rework, speed coordination, and expose the right diagram or page at the right moment.",
            "Portfolio planning should assume continual parser, model, and retrieval upgrades rather than one static architecture.",
        ],
        watch_items=[
            "Review scenario assumptions quarterly against labor, carbon, and delivery signals.",
            "Track whether your corpus design still supports cross-source questions as document volume grows.",
            "Use citation and figure-evidence analytics to identify where answers are strong and where the corpus still needs structure work.",
        ],
        diagram_style="quadrant",
        diagram_caption="A scenario matrix spanning information maturity against delivery pressure in the construction industry.",
        references=[
            "GlobalABC Global Status Report for Buildings and Construction 2024/2025",
            "International Labour Organization Construction Sector Overview",
            "NIBS Digital Twins for the Built Environment",
            "Autodesk 2025 State of Design & Make: Spotlight on Construction",
        ],
    ),
]

POWER_SYSTEM_TRANSFORMATION_SECTIONS: list[ResearchSection] = [
    ResearchSection(
        title="The Age Of Electricity",
        thesis=(
            "Power systems are entering an electricity-led growth cycle driven by electrification, cooling, industry, transport, "
            "and digital infrastructure, which makes grid readiness the foundation for wider economic strategy."
        ),
        signals=[
            "Electricity demand is rising again after years of flatter growth in many advanced economies as transport, buildings, and industrial processes electrify.",
            "Demand growth is no longer only a developing-economy story because digital infrastructure, air conditioning, and reindustrialization are lifting load in mature markets too.",
            "Policy and planning assumptions built around slower load growth are now under pressure, especially where large new electric loads appear faster than transmission upgrades.",
            "The energy transition is becoming more operationally complex because demand growth, decarbonization, and reliability now have to be solved together rather than sequentially.",
        ],
        implications=[
            "Knowledge systems for the power sector should preserve planning assumptions, study dates, and source lineage because grid decisions depend on time-sensitive evidence.",
            "Large energy corpora should keep policy, market, engineering, and asset documents linked rather than flattening them into one generic text pool.",
            "Grounded retrieval becomes more valuable as utilities and planners need to compare forecasts, interconnection data, and resilience guidance across many sources.",
        ],
        watch_items=[
            "Track where load-growth assumptions change faster than planning cycles.",
            "Measure whether demand-side and supply-side evidence are retrieved together or in isolation.",
            "Preserve region, balancing-area, and planning-horizon metadata because electricity questions are highly context dependent.",
        ],
        diagram_style="curve",
        diagram_caption="A demand-growth curve showing electricity becoming the common operating layer for transport, buildings, industry, and digital infrastructure.",
        references=[
            "IEA Electricity 2026",
            "EIA Annual Energy Outlook 2026",
        ],
    ),
    ResearchSection(
        title="AI, Data Centres, And Large Loads",
        thesis=(
            "AI and data centres are now planning-significant loads, forcing utilities, regulators, and developers to think about power availability, timing, and flexibility much earlier."
        ),
        signals=[
            "Data-centre expansion is becoming a material driver of commercial electricity demand growth in long-range outlooks.",
            "Large-load projects are testing existing interconnection, siting, and permitting processes because developers need power certainty earlier in the project lifecycle.",
            "The conversation has shifted from abstract AI energy concerns to concrete questions about where loads can connect, what flexibility is available, and how resilience is maintained.",
            "Load growth from AI is intertwined with local grid constraints, transmission access, and generation mix, so national averages can hide severe regional bottlenecks.",
        ],
        implications=[
            "Document ingestion for energy planning should preserve study boundaries such as utility territory, substation, queue, and forecast scenario rather than only source document boundaries.",
            "Grounded answers about AI power demand should retrieve both long-range outlook content and local grid constraints because one without the other is operationally incomplete.",
            "Architecture diagrams are useful in this domain because stakeholders need to see how load requests, planning studies, and grounded retrieval connect into one evidence flow.",
        ],
        watch_items=[
            "Track whether large-load questions require utility, policy, and technology evidence together.",
            "Watch for situations where the answer depends on transmission timing rather than total generation capacity.",
            "Preserve timestamps because AI-load narratives can become stale quickly as projects move through planning gates.",
        ],
        diagram_style="bar",
        diagram_caption="A load-mix bar chart showing the growing role of AI and data-centre demand alongside electrification and conventional consumption growth.",
        references=[
            "IEA Key Questions on Energy and AI",
            "EIA Annual Energy Outlook 2026",
            "DOE FY 2026 Volume 3",
        ],
    ),
    ResearchSection(
        title="Grid Capacity And Connection Queues",
        thesis=(
            "Grid bottlenecks are becoming one of the main constraints on both clean-energy deployment and new electric load growth, making queues and connection readiness central planning signals."
        ),
        signals=[
            "Grid connection queues have reached record levels in many regions, slowing the delivery of supply, storage, and new demand projects.",
            "Connection delays are not only engineering problems; they also reflect planning, permitting, coordination, and market-design bottlenecks.",
            "A queue-heavy environment changes project risk because a generation or load asset can be economically ready before the network path is ready.",
            "As more projects wait in the queue, the value of high-quality interconnection studies, timeline assumptions, and regional planning evidence rises sharply.",
        ],
        implications=[
            "Energy corpora should preserve queue identifiers, planning region tags, and connection-stage metadata because these attributes often drive answer relevance.",
            "Chunking should avoid splitting tables or notes that define project stage, network constraint, or study outcome.",
            "Index freshness matters because queue conditions and connection assumptions evolve over time and stale answers are operationally dangerous.",
        ],
        watch_items=[
            "Track how often users ask questions that span both generation and load queues.",
            "Measure whether region metadata improves retrieval precision in interconnection questions.",
            "Preserve structured tables intact when they contain stage, status, or capacity values.",
        ],
        diagram_style="chain",
        diagram_caption="A queue-to-connection chain showing how projects move from request to study, upgrade, energization, and operational service.",
        references=[
            "IEA Electricity 2026 - Grids",
            "IEA Electricity Grids and Secure Energy Transitions",
        ],
    ),
    ResearchSection(
        title="Flexibility, Storage, And Demand Response",
        thesis=(
            "As demand rises and generation portfolios diversify, flexibility becomes a core system capability delivered through storage, demand response, smarter controls, and coordinated operations."
        ),
        signals=[
            "Power systems need more flexibility to integrate changing supply patterns and increasingly dynamic demand profiles.",
            "Demand-side resources and storage are becoming planning tools rather than niche add-ons because they can defer grid upgrades or reduce peak stress.",
            "Grid modernization is increasingly about orchestration and visibility, not only about adding hardware.",
            "System flexibility depends on data access, forecasting, coordination, and control-room confidence as much as on installed storage capacity.",
        ],
        implications=[
            "Retrieval systems for power planning should preserve control strategy, operating constraint, and scenario context so flexibility guidance is not detached from its assumptions.",
            "Knowledge graphs around storage and demand response become more useful when users can retrieve both policy guidance and operating practice together.",
            "Agentic retrieval is useful for questions that combine load shape, storage timing, and planning alternatives across multiple documents.",
        ],
        watch_items=[
            "Track whether demand-response evidence is requested together with transmission or generation evidence.",
            "Measure the retrieval value of preserving scenario labels and operating assumptions.",
            "Watch where a table, chart, and narrative paragraph must be returned together to answer a flexibility question well.",
        ],
        diagram_style="loop",
        diagram_caption="A system-flexibility loop connecting load forecasting, demand response, storage dispatch, operator action, and reliability outcomes.",
        references=[
            "IEA Electricity 2026",
            "NREL Status of Power System Transformation",
        ],
    ),
    ResearchSection(
        title="Renewables, Electrification, And Fossil Transition",
        thesis=(
            "Renewables, electrification, and grid enhancement increasingly have to be planned as one transition package rather than as independent policy tracks."
        ),
        signals=[
            "Renewable capacity continues to expand quickly, but deployment value depends on how well grids, storage, and electrified demand are coordinated around it.",
            "Countries are being pushed to connect renewable growth with practical grid-enhancement programs rather than treating generation and networks as separate investment streams.",
            "Electrification is becoming a security and competitiveness question as well as a decarbonization question.",
            "The transition away from fossil fuels depends on both new clean supply and the network capacity to move and use it effectively.",
        ],
        implications=[
            "Energy-transition corpora should preserve the linkage between generation plans, grid plans, and end-use electrification evidence.",
            "Retrieval quality improves when tables, targets, and narrative justifications remain tied together through section-aware chunking.",
            "Grounded answers should cite whether a claim came from capacity expansion, grid enhancement, or electrification planning because those are different evidence categories.",
        ],
        watch_items=[
            "Track whether transition questions require both emissions and grid-delivery evidence.",
            "Watch where policy targets outrun network execution capacity.",
            "Preserve technology, geography, and timeframe metadata because transition narratives depend heavily on all three.",
        ],
        diagram_style="balance",
        diagram_caption="A transition balance comparing renewable build-out, electrification demand, network readiness, and system affordability.",
        references=[
            "IRENA Transitioning away from fossil fuels (2026)",
            "IRENA Renewable Capacity Statistics 2026",
            "IEA Electricity 2026",
        ],
    ),
    ResearchSection(
        title="Transmission Planning And Regional Coordination",
        thesis=(
            "Transmission planning is becoming a strategic coordination discipline because decarbonized, load-growing systems need more regional visibility, larger build programs, and better timing."
        ),
        signals=[
            "Interregional transmission can improve reliability, lower system cost, and support higher renewable penetration in many future scenarios.",
            "Planning now has to coordinate utility, market, policy, and developer perspectives instead of treating transmission as a slower back-office process.",
            "Transmission value is often systemic, which makes it easy to underbuild when planning or evidence remains fragmented.",
            "The timing mismatch between demand growth and transmission build-out is emerging as a persistent execution risk.",
        ],
        implications=[
            "Transmission documents should be indexed with region, timeframe, and scenario metadata so questions can target the right planning horizon.",
            "Chunking should preserve the coherence of study findings, alternative cases, and benefit statements rather than slicing them into generic fragments.",
            "Knowledge bases become more useful when users can compare queue conditions, study assumptions, and corridor options across documents.",
        ],
        watch_items=[
            "Track where transmission answers need cross-document synthesis rather than single-report lookup.",
            "Measure whether scenario labels and regional tags improve retrieval over plain text similarity.",
            "Preserve planning-case names intact because they often carry the main semantic boundary in power studies.",
        ],
        diagram_style="matrix",
        diagram_caption="A planning matrix mapping region, time horizon, transmission option, and system benefit across coordinated grid cases.",
        references=[
            "NREL Powered By: Transmission Planning",
            "DOE Grid Modernization Initiative",
            "NREL Status of Power System Transformation",
        ],
    ),
    ResearchSection(
        title="Reliability, Resilience, And Security",
        thesis=(
            "Reliable power systems now have to withstand weather disruption, infrastructure stress, cyber risk, and changing generation mixes at the same time."
        ),
        signals=[
            "Grid modernization now explicitly includes resilience, storage, transmission efficiency, and cyber-physical security responsibilities.",
            "Resilience is not a single technology choice; it spans planning, operations, emergency preparedness, asset hardening, and demand-side coordination.",
            "As systems decentralize and digitalize, information quality becomes part of reliability because operators and planners depend on trustworthy situational evidence.",
            "Reliability studies and resilience guidance must be interpreted together, especially where clean-energy integration and severe-weather exposure overlap.",
        ],
        implications=[
            "Power-sector document systems should preserve disturbance context, region, asset scope, and study purpose so reliability evidence remains usable after ingestion.",
            "Image and diagram handling matter here because many resilience and reliability artifacts are maps, one-line diagrams, control schematics, and planning figures.",
            "Grounded answers should separate routine planning evidence from emergency or resilience guidance to avoid operational confusion.",
        ],
        watch_items=[
            "Track when questions require both reliability and resilience evidence instead of one or the other.",
            "Measure how often figure evidence is necessary to explain grid topology or contingency context.",
            "Preserve control notes, figure captions, and map context rather than only paragraph text.",
        ],
        diagram_style="stack",
        diagram_caption="A resilience stack showing planning, operations, transmission, distributed resources, and emergency response as layered reliability controls.",
        references=[
            "DOE Office of Electricity Strategic Plan 2026",
            "NREL Power Systems Resilience",
            "DOE Grid Modernization Division",
        ],
    ),
    ResearchSection(
        title="Capital, Permitting, And Delivery Models",
        thesis=(
            "The grid transition is now limited as much by delivery capacity, permitting speed, and investment coordination as by technology availability."
        ),
        signals=[
            "Grid and storage investment needs remain far above current deployment rates in many transition pathways.",
            "Investors need clearer, planning-linked project pipelines before capital can move fast enough into network enhancement.",
            "Permitting and delivery friction can erase the value of good long-range strategy if projects cannot be executed on time.",
            "Public-private coordination is increasingly necessary because grid expansion relies on regulated assets, private capital, and public planning frameworks all at once.",
        ],
        implications=[
            "Corpus design should preserve investment assumptions, permitting status, and delivery dependencies because these often explain why a plan is late or feasible.",
            "Incremental indexing matters in this domain because schedules, approvals, and capital programs change continuously.",
            "Knowledge interfaces should let users compare narrative strategy with delivery readiness, not only with stated targets.",
        ],
        watch_items=[
            "Track whether project-delivery questions depend on financing, permitting, and engineering evidence together.",
            "Measure the freshness requirement for approval and build-status data.",
            "Preserve sequence and dependency language because grid programs are often path dependent.",
        ],
        diagram_style="ladder",
        diagram_caption="A delivery ladder moving from strategy to permitting, capital commitment, build execution, and energized infrastructure.",
        references=[
            "IRENA Funding Grid and Storage Enhancement (2026)",
            "IRENA Transitioning away from fossil fuels (2026)",
            "DOE Grid Modernization Initiative",
        ],
    ),
    ResearchSection(
        title="Grid Intelligence And Knowledge Architecture",
        thesis=(
            "As grid planning and operations become more document-intensive, utilities and policymakers need governed retrieval systems that can combine studies, policies, diagrams, and operating guidance into one answer path."
        ),
        signals=[
            "Electric-sector decisions increasingly span policy memos, planning studies, interconnection tables, resilience guidance, and technical diagrams.",
            "The same question can require evidence from both narrative reports and figure-heavy planning artifacts, which makes multimodal parsing and evidence serving materially useful.",
            "Architecture choices around segmentation, normalization, figure extraction, and provenance directly affect whether a grounded answer remains trustworthy.",
            "Search-oriented system diagrams help domain teams understand how raw energy documents become retrieval-ready evidence and then grounded answers.",
        ],
        implications=[
            "The ingestion pipeline should split only for extractor limits, then reunify, normalize, preserve figures, and emit coherent retrieval chunks.",
            "Energy knowledge bases should return both text citations and diagram evidence when one-line diagrams, maps, or planning figures are relevant.",
            "Agentic retrieval is especially helpful for electric-sector questions because one answer often spans forecasts, planning constraints, and resilience guidance.",
        ],
        watch_items=[
            "Track when figure evidence changes the quality of answers about network topology or planning flow.",
            "Measure how often subquery planning is needed for cross-source energy questions.",
            "Keep parser, chunker, and publishing adapters swappable because utility content maturity varies widely.",
        ],
        diagram_style="architecture",
        diagram_caption="A grid-intelligence architecture showing source studies, parsing, chunking, Search publishing, agentic retrieval, and grounded assistant synthesis.",
        references=[
            "DOE Grid Modernization Initiative",
            "NREL Status of Power System Transformation",
            "IEA Electricity 2026",
        ],
    ),
    ResearchSection(
        title="Scenarios For 2030",
        thesis=(
            "The most useful power-sector outlook is not one prediction but a scenario set that tests how load growth, grid enhancement, flexibility, and policy execution interact by 2030."
        ),
        signals=[
            "One scenario assumes strong electrification and AI load growth matched by transmission, storage, and planning reform.",
            "Another assumes demand rises quickly while grid enhancement and permitting lag, producing persistent congestion and localized reliability stress.",
            "A more balanced scenario depends on flexible demand, smarter operations, and selective infrastructure acceleration rather than only on large capital build-out.",
            "Across scenarios, the common differentiator is whether planning evidence stays current, connected, and operationally usable.",
        ],
        implications=[
            "Scenario work benefits from corpora that preserve versioned assumptions, figure evidence, and planning-case names over time.",
            "Grounded assistants are most useful when they can explain not only what a scenario says but which evidence set, region, and timeframe it came from.",
            "The best preparation is an architecture that supports continual re-indexing, strong provenance, and cross-source retrieval rather than a one-time static report load.",
        ],
        watch_items=[
            "Review scenario assumptions as load forecasts, connection queues, and grid investments change.",
            "Measure where answer quality depends on up-to-date planning evidence rather than model fluency.",
            "Use citation analytics to see which scenario sections actually anchor user questions.",
        ],
        diagram_style="quadrant",
        diagram_caption="A 2030 scenario matrix spanning load-growth pressure against grid-enhancement readiness.",
        references=[
            "IEA Electricity 2026",
            "EIA Annual Energy Outlook 2026",
            "IRENA Transitioning away from fossil fuels (2026)",
        ],
    ),
]


GENERATIVE_AI_BLUEPRINT = ResearchReportBlueprint(
    topic_key="future-of-generative-ai",
    file_stem="generative-ai-futures-report",
    report_title="Future of Generative AI",
    report_subtitle="Enterprise Foresight Compendium",
    sections=GENERATIVE_AI_FUTURES_SECTIONS,
)

CONSTRUCTION_BLUEPRINT = ResearchReportBlueprint(
    topic_key="construction-industry-blueprint",
    file_stem="construction-industry-blueprint-report",
    report_title="Future of Construction Industry",
    report_subtitle="Digital Delivery, Sustainability, And Knowledge Architecture",
    sections=CONSTRUCTION_INDUSTRY_SECTIONS,
)

POWER_SYSTEM_BLUEPRINT = ResearchReportBlueprint(
    topic_key="power-system-transformation",
    file_stem="power-system-transformation-report",
    report_title="Power Systems In The Age Of Electricity",
    report_subtitle="Grid Modernization, AI Load Growth, And Resilient Delivery",
    sections=POWER_SYSTEM_TRANSFORMATION_SECTIONS,
)

RESEARCH_REPORT_BLUEPRINTS: dict[str, ResearchReportBlueprint] = {
    GENERATIVE_AI_BLUEPRINT.topic_key: GENERATIVE_AI_BLUEPRINT,
    CONSTRUCTION_BLUEPRINT.topic_key: CONSTRUCTION_BLUEPRINT,
    POWER_SYSTEM_BLUEPRINT.topic_key: POWER_SYSTEM_BLUEPRINT,
}


def create_random_research_corpus(
    page_count: int | None = None,
    topic: str | None = None,
) -> GeneratedSample:
    total_pages = page_count or (settings.hard_page_split_threshold + 5)
    blueprint = _resolve_research_blueprint(topic)
    return _create_research_report_sample(
        blueprint,
        page_count=total_pages,
        minimum_pages=settings.hard_page_split_threshold + 1,
    )


def create_generative_ai_futures_report(page_count: int = 520) -> GeneratedSample:
    return _create_research_report_sample(GENERATIVE_AI_BLUEPRINT, page_count=page_count, minimum_pages=501)


def create_construction_industry_report(page_count: int = 540) -> GeneratedSample:
    return _create_research_report_sample(CONSTRUCTION_BLUEPRINT, page_count=page_count, minimum_pages=501)


def _resolve_research_blueprint(topic: str | None) -> ResearchReportBlueprint:
    if topic:
        normalized = _slugify(topic).strip("-")
        blueprint = RESEARCH_REPORT_BLUEPRINTS.get(normalized)
        if blueprint is None:
            raise ValueError(
                f"Unknown topic '{topic}'. Available topics: {', '.join(sorted(RESEARCH_REPORT_BLUEPRINTS))}."
            )
        return blueprint
    return random.choice(list(RESEARCH_REPORT_BLUEPRINTS.values()))


def _create_research_report_sample(
    blueprint: ResearchReportBlueprint,
    *,
    page_count: int,
    minimum_pages: int,
) -> GeneratedSample:
    if page_count < minimum_pages:
        raise ValueError(f"{blueprint.report_title} sample must be at least {minimum_pages} pages.")
    if canvas is None or Image is None or ImageReader is None:
        raise RuntimeError("reportlab and pillow are required to generate the research report sample.")

    file_name = _build_sample_file_name(blueprint.file_stem, page_count)
    path = settings.uploads_dir / file_name
    diagram_dir = settings.artifacts_dir / f"{path.stem}_diagrams"
    diagram_dir.mkdir(parents=True, exist_ok=True)
    diagram_paths = [_build_section_diagram(section, index + 1, diagram_dir) for index, section in enumerate(blueprint.sections)]
    _render_research_report_pdf(
        path,
        page_count,
        blueprint.sections,
        diagram_paths,
        report_title=blueprint.report_title,
        report_subtitle=blueprint.report_subtitle,
    )
    return GeneratedSample(
        path=path,
        page_count=page_count,
        file_name=file_name,
        section_interval=max(1, math.ceil(page_count / len(blueprint.sections))),
        topic_key=blueprint.topic_key,
        report_title=blueprint.report_title,
    )


def _build_sample_file_name(file_stem: str, page_count: int) -> str:
    return f"{file_stem}-{page_count}-pages-{uuid4().hex[:8]}.pdf"


def _render_research_report_pdf(
    path: Path,
    page_count: int,
    sections: list[ResearchSection],
    diagram_paths: list[Path],
    report_title: str,
    report_subtitle: str,
) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    pages_per_section = math.ceil(page_count / len(sections))
    page_number = 1
    for section_index, section in enumerate(sections, start=1):
        for section_page in range(1, pages_per_section + 1):
            if page_number > page_count:
                break
            _render_futures_page(
                pdf=pdf,
                width=width,
                height=height,
                global_page=page_number,
                total_pages=page_count,
                section=section,
                section_index=section_index,
                section_page=section_page,
                section_total=pages_per_section,
                diagram_path=diagram_paths[section_index - 1],
                report_title=report_title,
                report_subtitle=report_subtitle,
            )
            pdf.showPage()
            page_number += 1
    pdf.save()


def _render_futures_page(
    *,
    pdf,
    width: float,
    height: float,
    global_page: int,
    total_pages: int,
    section: ResearchSection,
    section_index: int,
    section_page: int,
    section_total: int,
    diagram_path: Path,
    report_title: str,
    report_subtitle: str,
) -> None:
    margin_x = 54
    cursor_y = height - 56

    pdf.setFont("Helvetica-Bold", 19)
    pdf.drawString(margin_x, cursor_y, f"Section {section_index}. {section.title}")
    cursor_y -= 18

    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        margin_x,
        cursor_y,
        f"{report_title}: {report_subtitle} | Page {global_page} of {total_pages}",
    )
    cursor_y -= 22

    pdf.setFillColorRGB(0.10, 0.18, 0.28)
    pdf.rect(margin_x, cursor_y - 26, width - (margin_x * 2), 26, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(
        margin_x + 8,
        cursor_y - 18,
        f"Section thesis | section page {section_page} of {section_total}",
    )
    pdf.setFillColorRGB(0, 0, 0)
    cursor_y -= 40

    cursor_y = _draw_wrapped_paragraph(pdf, section.thesis, margin_x, cursor_y, width - (margin_x * 2), 11, 14)

    if section_page == 1:
        pdf.drawImage(str(diagram_path), margin_x, cursor_y - 220, width=500, height=200, preserveAspectRatio=True, mask="auto")
        cursor_y -= 232
        cursor_y = _draw_wrapped_paragraph(
            pdf,
            f"Figure {section_index}. {section.diagram_caption}",
            margin_x,
            cursor_y,
            width - (margin_x * 2),
            9,
            12,
        )
        cursor_y = _draw_wrapped_paragraph(
            pdf,
            "Research anchors: " + "; ".join(section.references),
            margin_x,
            cursor_y - 4,
            width - (margin_x * 2),
            9,
            12,
        )
    elif section_page % 13 == 0:
        pdf.drawImage(str(diagram_path), width - 220, cursor_y - 110, width=160, height=90, preserveAspectRatio=True, mask="auto")
        cursor_y -= 8

    cycle_index = section_page - 1
    narrative_blocks = [
        (
            f"Signal snapshot {section_page}: {section.signals[cycle_index % len(section.signals)]} "
            f"This page treats the signal as a planning input rather than a prediction, because the section focuses "
            f"on how enterprise document and retrieval systems should respond to fast-moving model and market conditions."
        ),
        (
            f"Enterprise implication {section_page}: {section.implications[cycle_index % len(section.implications)]} "
            f"In a large knowledge platform, this translates into decisions about chunking policy, evidence handling, human review, "
            f"and which workflows should tolerate model variability versus require deterministic fallback."
        ),
        (
            f"Watch item {section_page}: {section.watch_items[cycle_index % len(section.watch_items)]} "
            f"Teams should log these signals as operating indicators so they can revisit corpus preparation, access control, "
            f"retrieval settings, and model routing without rebuilding the entire ingestion estate."
        ),
        (
            f"Scenario note {section_page}: Section {section_index} is intentionally expanded across many pages so the sample behaves "
            f"like a long-form enterprise foresight report. The repeated structure forces the ingestion pipeline to preserve headings, "
            f"page numbers, figure captions, and section breadcrumbs across a large but still semantically coherent corpus."
        ),
    ]

    for block in narrative_blocks:
        cursor_y = _draw_wrapped_paragraph(pdf, block, margin_x, cursor_y, width - (margin_x * 2), 10, 13)
        cursor_y -= 4

    if section_page % 4 == 0:
        cursor_y = _draw_small_table(
            pdf,
            margin_x,
            cursor_y,
            [
                ("Focus", section.title),
                ("Primary signal", section.signals[cycle_index % len(section.signals)]),
                ("Design implication", section.implications[(cycle_index + 1) % len(section.implications)]),
            ],
            width - (margin_x * 2),
        )

    if cursor_y < 90:
        cursor_y = 90

    pdf.setStrokeColorRGB(0.82, 0.86, 0.90)
    pdf.line(margin_x, 58, width - margin_x, 58)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin_x, 44, f"Section references: {', '.join(section.references)}")


def _draw_wrapped_paragraph(pdf, text: str, x: float, y: float, width: float, font_size: int, leading: int) -> float:
    pdf.setFont("Helvetica", font_size)
    wrapped = _wrap_text(text, max(50, int(width // (font_size * 0.55))))
    text_obj = pdf.beginText(x, y)
    text_obj.setLeading(leading)
    for line in wrapped:
        text_obj.textLine(line)
    pdf.drawText(text_obj)
    return y - (leading * len(wrapped)) - 6


def _draw_small_table(pdf, x: float, y: float, rows: list[tuple[str, str]], width: float) -> float:
    row_height = 18
    table_height = row_height * len(rows)
    pdf.setFillColorRGB(0.96, 0.97, 0.99)
    pdf.rect(x, y - table_height, width, table_height, fill=1, stroke=0)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont("Helvetica-Bold", 9)
    current_y = y - 13
    for label, value in rows:
        pdf.drawString(x + 8, current_y, label)
        pdf.setFont("Helvetica", 9)
        value_line = _truncate_for_table(value, 78)
        pdf.drawString(x + 118, current_y, value_line)
        pdf.setFont("Helvetica-Bold", 9)
        current_y -= row_height
    return y - table_height - 12


def _truncate_for_table(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _wrap_text(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, width=width, break_long_words=False, replace_whitespace=False)


def _build_section_diagram(section: ResearchSection, section_number: int, output_dir: Path) -> Path:
    output_path = output_dir / f"section_{section_number:02d}_{_slugify(section.title)}.png"
    image = Image.new("RGB", (1200, 720), "#F4F6F8")
    draw = ImageDraw.Draw(image)
    title_font = _load_font(42)
    body_font = _load_font(24)
    small_font = _load_font(18)
    draw.text((48, 36), f"Section {section_number}: {section.title}", fill="#0F2438", font=title_font)
    draw.text((48, 96), section.diagram_caption, fill="#36506A", font=small_font)
    drawer = DIAGRAM_DRAWERS.get(section.diagram_style, _draw_matrix_diagram)
    drawer(draw, section, body_font, small_font)
    image.save(output_path)
    return output_path


def _load_font(size: int):
    if ImageFont is None:
        return None
    for candidate in ["arial.ttf", "segoeui.ttf", "calibri.ttf"]:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_curve_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    origin = (110, 600)
    draw.line((origin[0], origin[1], 1050, origin[1]), fill="#4C6278", width=4)
    draw.line((origin[0], origin[1], origin[0], 170), fill="#4C6278", width=4)
    points = [(180, 560), (340, 500), (520, 420), (710, 300), (930, 220)]
    draw.line(points, fill="#0B84F3", width=8)
    labels = ["Assistants", "Code", "Multimodal", "Agents", "Adaptive systems"]
    for (x, y), label in zip(points, labels):
        draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill="#F97316", outline="#F97316")
        draw.text((x - 40, y - 36), label, fill="#163047", font=small_font)
    draw.text((120, 628), "Time", fill="#163047", font=body_font)
    draw.text((56, 176), "Capability", fill="#163047", font=body_font)


def _draw_bar_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    x_positions = [180, 390, 600, 810]
    heights = [180, 310, 430, 520]
    labels = ["Access", "Usage", "Workflow", "Transformation"]
    colors = ["#93C5FD", "#60A5FA", "#2563EB", "#1D4ED8"]
    for x, height, label, color in zip(x_positions, heights, labels, colors):
        draw.rectangle((x, 600 - height, x + 120, 600), fill=color, outline=color)
        draw.text((x + 10, 614), label, fill="#163047", font=small_font)
    draw.line((130, 600, 1000, 600), fill="#4C6278", width=4)
    draw.line((130, 600, 130, 170), fill="#4C6278", width=4)
    draw.text((138, 170), "Depth of adoption", fill="#163047", font=body_font)


def _draw_ladder_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    steps = [
        ("Low exposure", "#DCFCE7"),
        ("Task assist", "#BBF7D0"),
        ("Workflow redesign", "#86EFAC"),
        ("Supervised automation", "#4ADE80"),
    ]
    x, y = 180, 560
    for index, (label, color) in enumerate(steps):
        draw.rectangle((x + index * 140, y - index * 80, x + 110 + index * 140, y + 40 - index * 80), fill=color, outline="#166534", width=3)
        draw.text((x + 10 + index * 140, y - 52 - index * 80), label, fill="#163047", font=small_font)
    draw.text((160, 618), "Increasing task exposure", fill="#163047", font=body_font)


def _draw_flywheel_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    boxes = [
        (260, 220, "Better tools"),
        (700, 220, "Faster experiments"),
        (700, 470, "Workflow redesign"),
        (260, 470, "Compounding value"),
    ]
    for x, y, label in boxes:
        draw.rounded_rectangle((x, y, x + 220, y + 90), radius=18, fill="#E0F2FE", outline="#0284C7", width=3)
        draw.text((x + 20, y + 30), label, fill="#163047", font=body_font)
    arrows = [(480, 265, 700, 265), (810, 310, 810, 470), (700, 515, 480, 515), (370, 470, 370, 310)]
    for arrow in arrows:
        draw.line(arrow, fill="#0284C7", width=6)


def _draw_loop_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    nodes = [
        ((510, 180), "Intent"),
        ((820, 310), "Retrieval"),
        ((760, 560), "Action"),
        ((300, 560), "Human review"),
        ((220, 310), "Policy"),
    ]
    for (x, y), label in nodes:
        draw.ellipse((x - 90, y - 45, x + 90, y + 45), fill="#F5F3FF", outline="#7C3AED", width=3)
        draw.text((x - 48, y - 10), label, fill="#163047", font=small_font)
    loop = [(600, 220), (780, 300), (720, 520), (360, 520), (260, 320), (600, 220)]
    draw.line(loop, fill="#7C3AED", width=6, joint="curve")


def _draw_balance_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    draw.line((600, 210, 600, 540), fill="#475569", width=8)
    draw.line((350, 290, 850, 250), fill="#475569", width=8)
    items = [
        ((250, 320, 430, 420), "Safety"),
        ((430, 330, 610, 430), "Privacy"),
        ((650, 260, 830, 360), "Transparency"),
        ((830, 250, 1010, 350), "Performance"),
    ]
    for rect, label in items:
        draw.rounded_rectangle(rect, radius=16, fill="#FEF3C7", outline="#B45309", width=3)
        draw.text((rect[0] + 24, rect[1] + 34), label, fill="#163047", font=body_font)


def _draw_stack_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    layers = [
        ("Applications and agents", "#DBEAFE"),
        ("Model serving and routing", "#BFDBFE"),
        ("Accelerators and memory", "#93C5FD"),
        ("Data centers and cooling", "#60A5FA"),
        ("Grid, gas, nuclear, renewables", "#2563EB"),
    ]
    top = 210
    for index, (label, color) in enumerate(layers):
        y = top + index * 82
        draw.rounded_rectangle((250, y, 950, y + 58), radius=16, fill=color, outline="#1D4ED8", width=2)
        draw.text((282, y + 16), label, fill="#163047", font=body_font)


def _draw_matrix_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    draw.rectangle((220, 200, 980, 590), outline="#475569", width=4)
    draw.line((600, 200, 600, 590), fill="#475569", width=3)
    draw.line((220, 395, 980, 395), fill="#475569", width=3)
    labels = [
        ((300, 260), "Infra"),
        ((690, 260), "Data"),
        ((300, 455), "Models"),
        ((690, 455), "Talent"),
    ]
    for (x, y), label in labels:
        draw.text((x, y), label, fill="#163047", font=body_font)


def _draw_chain_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    labels = ["Models", "Platforms", "Data", "Workflows", "Distribution"]
    x = 130
    for label in labels:
        draw.rounded_rectangle((x, 320, x + 160, 400), radius=16, fill="#DCFCE7", outline="#166534", width=3)
        draw.text((x + 28, 350), label, fill="#163047", font=body_font)
        if label != labels[-1]:
            draw.line((x + 160, 360, x + 200, 360), fill="#166534", width=5)
        x += 200


def _draw_quadrant_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    draw.rectangle((220, 180, 980, 590), outline="#334155", width=4)
    draw.line((600, 180, 600, 590), fill="#334155", width=3)
    draw.line((220, 385, 980, 385), fill="#334155", width=3)
    draw.text((250, 210), "High capability / Low readiness", fill="#163047", font=small_font)
    draw.text((650, 210), "High capability / High readiness", fill="#163047", font=small_font)
    draw.text((250, 420), "Low capability / Low readiness", fill="#163047", font=small_font)
    draw.text((650, 420), "Steady utility", fill="#163047", font=small_font)


def _draw_architecture_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    boxes = [
        ((70, 230, 260, 430), "#E0F2FE", "Project sources", ["BIM / drawings", "RFIs / submittals", "Photos / reports", "Permits / safety docs"]),
        ((330, 210, 540, 450), "#DCFCE7", "Ingestion plane", ["Layout / OCR", "Figure extraction", "Normalization", "Chunking + metadata"]),
        ((610, 230, 820, 430), "#FEF3C7", "Search plane", ["Index + KB", "Agentic retrieval", "Subquery planning", "Citations"]),
        ((890, 250, 1110, 410), "#F5F3FF", "Grounded answers", ["GPT-5.4 synthesis", "Text + image evidence", "Project controls", "Audit trail"]),
    ]
    for rect, color, title, lines in boxes:
        draw.rounded_rectangle(rect, radius=18, fill=color, outline="#334155", width=3)
        draw.text((rect[0] + 18, rect[1] + 18), title, fill="#163047", font=body_font)
        for line_index, line in enumerate(lines):
            draw.text((rect[0] + 18, rect[1] + 56 + (line_index * 30)), line, fill="#36506A", font=small_font)

    arrows = [
        (260, 330, 330, 330),
        (540, 330, 610, 330),
        (820, 330, 890, 330),
    ]
    for x1, y1, x2, y2 in arrows:
        draw.line((x1, y1, x2, y2), fill="#0F766E", width=6)
        draw.polygon([(x2, y2), (x2 - 18, y2 - 10), (x2 - 18, y2 + 10)], fill="#0F766E")

    draw.text((355, 500), "Architecture focus: preserve revision-aware evidence for search and grounded chat", fill="#163047", font=small_font)


def _draw_blueprint_background(draw, title_font, small_font, sheet_title: str, sheet_code: str) -> None:
    draw.rectangle((0, 0, 1200, 720), fill="#082B52")
    for x in range(40, 1160, 60):
        draw.line((x, 40, x, 680), fill="#1C4E7F", width=1)
    for y in range(40, 680, 60):
        draw.line((40, y, 1160, y), fill="#1C4E7F", width=1)

    draw.rectangle((30, 30, 1170, 690), outline="#CFE7FF", width=3)
    draw.rectangle((850, 600, 1150, 675), outline="#CFE7FF", width=2)
    draw.line((850, 625, 1150, 625), fill="#CFE7FF", width=2)
    draw.line((970, 600, 970, 675), fill="#CFE7FF", width=2)
    draw.line((1055, 625, 1055, 675), fill="#CFE7FF", width=2)

    draw.text((54, 42), sheet_title, fill="#E7F2FF", font=title_font)
    draw.text((54, 88), "Blueprint-style technical exhibit for construction corpus grounding", fill="#A9D1FF", font=small_font)
    draw.text((865, 640), "Sheet", fill="#A9D1FF", font=small_font)
    draw.text((985, 640), sheet_code, fill="#E7F2FF", font=small_font)
    draw.text((1070, 640), "Scale NTS", fill="#E7F2FF", font=small_font)


def _draw_dimension_line(draw, start: tuple[int, int], end: tuple[int, int], label: str, font) -> None:
    x1, y1 = start
    x2, y2 = end
    draw.line((x1, y1, x2, y2), fill="#E7F2FF", width=2)
    draw.polygon([(x1, y1), (x1 + 10, y1 - 5), (x1 + 10, y1 + 5)], fill="#E7F2FF")
    draw.polygon([(x2, y2), (x2 - 10, y2 - 5), (x2 - 10, y2 + 5)], fill="#E7F2FF")
    label_x = min(x1, x2) + abs(x2 - x1) // 2 - 28
    label_y = min(y1, y2) - 24
    draw.text((label_x, label_y), label, fill="#E7F2FF", font=font)


def _draw_callout(draw, x: int, y: int, tag: str, text: str, small_font) -> None:
    draw.ellipse((x - 16, y - 16, x + 16, y + 16), outline="#E7F2FF", width=3)
    draw.text((x - 10, y - 9), tag, fill="#E7F2FF", font=small_font)
    draw.line((x + 16, y, x + 90, y - 18), fill="#E7F2FF", width=2)
    draw.text((x + 98, y - 32), text, fill="#A9D1FF", font=small_font)


def _draw_blueprint_building_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    title_font = _load_font(34)
    _draw_blueprint_background(draw, title_font, small_font, "CONSTRUCTION FLOOR PLAN / DIGITAL TWIN CONTEXT", "A-401")

    plan = (140, 170, 940, 560)
    draw.rectangle(plan, outline="#E7F2FF", width=4)
    for x in [300, 470, 650, 810]:
        draw.line((x, 170, x, 560), fill="#CFE7FF", width=3)
    for y in [270, 380, 470]:
        draw.line((140, y, 940, y), fill="#CFE7FF", width=3)

    room_labels = [
        (180, 210, "Lobby / Access"),
        (340, 210, "Core / Vertical"),
        (520, 210, "Project Control"),
        (700, 210, "Data / MEP Hub"),
        (180, 320, "Open Office"),
        (520, 320, "Coordination Bay"),
        (760, 320, "Safety Brief"),
        (180, 430, "Loading"),
        (360, 430, "Fabrication Staging"),
        (640, 430, "Commissioning"),
    ]
    for x, y, label in room_labels:
        draw.text((x, y), label, fill="#E7F2FF", font=small_font)

    for index, label in enumerate(["A", "B", "C", "D", "E"], start=0):
        x = 140 + (index * 170)
        draw.ellipse((x - 16, 128, x + 16, 160), outline="#E7F2FF", width=3)
        draw.text((x - 7, 134), label, fill="#E7F2FF", font=small_font)
    for index, label in enumerate(["1", "2", "3", "4"], start=0):
        y = 170 + (index * 110)
        draw.ellipse((96, y - 16, 128, y + 16), outline="#E7F2FF", width=3)
        draw.text((106, y - 9), label, fill="#E7F2FF", font=small_font)

    _draw_dimension_line(draw, (140, 595), (940, 595), "80.0 m overall", small_font)
    _draw_dimension_line(draw, (980, 170), (980, 560), "39.0 m", small_font)
    _draw_callout(draw, 720, 505, "1", "Twin link: BIM zone / mechanical asset graph", small_font)
    _draw_callout(draw, 250, 505, "2", "Lifecycle evidence: permits, RFIs, inspections", small_font)
    _draw_callout(draw, 585, 265, "3", "Field question hotspot: diagrams + specs + photos", small_font)

    draw.text((70, 620), "Legend: solid walls | grid refs | zone labels | dimension strings | lifecycle callouts", fill="#A9D1FF", font=small_font)


def _draw_blueprint_architecture_diagram(draw, section: ResearchSection, body_font, small_font) -> None:
    title_font = _load_font(34)
    _draw_blueprint_background(draw, title_font, small_font, "CONSTRUCTION KNOWLEDGE ARCHITECTURE / GROUNDED RETRIEVAL", "KA-102")

    boxes = [
        ((90, 220, 255, 500), "SOURCE SET", ["Plans / PDFs", "RFIs / submittals", "Site photos", "Safety docs"]),
        ((340, 185, 540, 535), "INGESTION", ["Layout + OCR", "Figure crops", "Intermediate JSON", "Section-aware chunks"]),
        ((625, 220, 835, 500), "SEARCH", ["Index + KB", "Agentic retrieve", "Subquery trace", "Citations"]),
        ((920, 240, 1100, 480), "ANSWER", ["GPT-5.4 synth", "Image evidence", "Chat UI", "Audit history"]),
    ]
    for rect, title, lines in boxes:
        draw.rectangle(rect, outline="#E7F2FF", width=3)
        draw.text((rect[0] + 14, rect[1] + 16), title, fill="#E7F2FF", font=body_font)
        for idx, line in enumerate(lines):
            draw.text((rect[0] + 16, rect[1] + 60 + (idx * 34)), line, fill="#A9D1FF", font=small_font)

    connector_y = 360
    for x1, x2, label in [(255, 340, "ETL-01"), (540, 625, "SRCH-02"), (835, 920, "ANS-03")]:
        draw.line((x1, connector_y, x2, connector_y), fill="#E7F2FF", width=3)
        draw.polygon([(x2, connector_y), (x2 - 14, connector_y - 8), (x2 - 14, connector_y + 8)], fill="#E7F2FF")
        draw.text((x1 + 8, connector_y - 28), label, fill="#A9D1FF", font=small_font)

    draw.rectangle((315, 80, 885, 145), outline="#E7F2FF", width=2)
    draw.text((340, 102), "CONTROL NOTES: revision-aware chunks | page anchors | figure evidence | grounded citations", fill="#E7F2FF", font=small_font)

    _draw_callout(draw, 470, 470, "A", "Segmentation protects DI limits and section coherence", small_font)
    _draw_callout(draw, 735, 470, "B", "Agentic retrieval can decompose multi-source queries", small_font)
    _draw_callout(draw, 995, 440, "C", "Answer returns text plus image evidence when relevant", small_font)

    _draw_dimension_line(draw, (90, 545), (1100, 545), "knowledge path 4 stages", small_font)
    draw.text((92, 585), "Sheet intent: provide diagram-grounded prompts about architecture, evidence flow, and retrieval control points", fill="#A9D1FF", font=small_font)


DIAGRAM_DRAWERS = {
    "architecture": _draw_architecture_diagram,
    "blueprint_architecture": _draw_blueprint_architecture_diagram,
    "blueprint_building": _draw_blueprint_building_diagram,
    "curve": _draw_curve_diagram,
    "bar": _draw_bar_diagram,
    "ladder": _draw_ladder_diagram,
    "flywheel": _draw_flywheel_diagram,
    "loop": _draw_loop_diagram,
    "balance": _draw_balance_diagram,
    "stack": _draw_stack_diagram,
    "matrix": _draw_matrix_diagram,
    "chain": _draw_chain_diagram,
    "quadrant": _draw_quadrant_diagram,
}


def _slugify(value: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")
