🪳 CockroachDB × AWS Hackathon:
CockroachDB and AWS invite developers, engineers, and AI builders to create the next generation of agentic applications. Harness CockroachDB's distributed AI capabilities, fully managed MCP Server, agent-ready ccloud CLI, open-source Agent Skills Repo, LangChain integrations and Claude/Cursor plugins - all on AWS - to build AI agents with production-grade, persistent memory.

Why Agentic Memory? Why Now?
AI agents are rapidly moving from experiments into real production workflows, like writing code, running pipelines, diagnosing incidents, and driving more application traffic than any human could. But here's the problem: agents need memory that never goes down.

An agent whose memory goes offline doesn't degrade gracefully, it stops. Traditional databases were optimized for human-scale reads and writes. Agentic systems are different: they spawn autonomously, write constantly, and require memory that persists across regions, failures, and scale  (with zero data loss and no maintenance windows).

CockroachDB was built for exactly this. It is the system of record for agentic memory: globally distributed, always-on, PostgreSQL-compatible, and now natively integrated into the agent toolchain through MCP, cloud, and an open-source skills ecosystem.

This hackathon is your invitation to build on that foundation.

Requirements
The Challenge
Build an agentic application that uses CockroachDB as its persistent memory layer, deployed on AWS.

Your agent should store, retrieve, and act on memory whether that's conversation history, user context, task state, embeddings, or structured transactional data. The best submissions will demonstrate that memory is not an afterthought, it is the thing that makes an agent useful in production.

All submissions must use at least two of the following CockroachDB tools:

CockroachDB Cloud Managed MCP Server — Connect AI agents directly to CockroachDB clusters with a single config snippet from the Cloud Console. Works natively with Claude Code, Cursor, and VS Code. Safe by default: read-only mode, full audit logging, zero custom proxy required. Endpoint: https://cockroachlabs.cloud/mcp
CockroachDB Distributed Vector Indexing — Store and query embeddings at scale using CockroachDB's vector support with distributed indexing. Semantic search and retrieval stay fast as your data grows — no separate vector store to maintain, no reindexing pain, and no consistency gaps between your vector data and your operational database. Ideal for RAG pipelines, long-term agent memory, and semantic search applications.
ccloud CLI (Agent-Ready) — Give your agent direct, secure access to the full CockroachDB Cloud control plane. Provision clusters, manage backups, configure networking, monitor audit logs — all from the terminal. Designed for AI with consistent noun-verb patterns, JSON output on every command, and granular service-account-based RBAC.
CockroachDB Agent Skills Repo (Open Source) — A curated, open-source collection of machine-executable Agent Skills encoding CockroachDB expertise. Skills span onboarding, query/schema design, operations, performance, security, and observability. Portable across Claude, Cursor, LangChain, and any MCP-compatible client.
All submissions must also use at least one AWS service:

Amazon Bedrock (foundation models, knowledge bases, or agents)
AWS Lambda (serverless agent execution)
Amazon ECS / EKS (containerized agent workloads)
Amazon S3 (artifact or document storage)
Amazon SageMaker (model training or inference)
Amazon Bedrock Agents (multi-step agentic workflows)
Any other AWS service that powers your agent's environment
 

What to Submit

Provide a URL to your public open source code repository for judging and testing.
The repository must contain all necessary source code, clear README documentation, any required dependencies, example configurations or datasets if applicable, and setup and run instructions required for the project to be functional. 
The repository must be public and open source by including an open source license file (we recommend MIT or Apache 2.0). This license should be detectable and visible at the top of the repository page (in the About section).  
Provide a URL to your functional demo app.
Include a video (less than 3 minutes) that demonstrates your submission and the CockroachDB memory layer at work. Videos must be uploaded to YouTube or Vimeo and made public.
Identify which CockroachDB tools you used (MCP Server, ccloud CLI, Distributed Vector Indexing, Agent Skills) and how — what did the agent actually do with them?
Identify which AWS Services tools you used (Amazon Bedrock, AWS Lambda, Amazon S3, etc.) and how.
Optional: Include an architectural diagram showing how CockroachDB, AWS services, and your agent interact.
Optional: Provide feedback on the CockroachDB AI tools or features.
Prizes
$8,750 in prizes
1st Place
$5,000 in cash
1 winner
• $5,000 in USD
• Blog feature,
• Cockroach Labs Swag

2nd Place
$2,500 in cash
1 winner
• $2,500 in USD
• Cockroach Labs Swag

3rd Place
$1,250 in cash
1 winner
• $1,250 in USD
• Cockroach Labs Swag

Devpost Achievements
Submitting to this hackathon could earn you:


X Hackathons
 level 14

Hackathon Winner
 level 3
Judges
A panel of qualified judges
A panel of qualified judges

Judging Criteria
Agentic Memory Design
Does CockroachDB play a meaningful, production-grade role as the agent's memory layer? Is it used for more than toy queries — state, embeddings, context, or transactional data at real scale?
Technical Implementation
Is the integration with CockroachDB tools (distributed vector index, MCP Server, ccloud CLI) quality software engineering? Does the agent use the tools correctly and safely?
Real-World Impact
How big of an impact could the project have on real users or workflows? Is the use case meaningful, not just technically impressive?
Production Readiness
Is the design secure, observable, and scalable? Has the team thought about resilience, access control, and what happens when things go wrong?
Creativity & Originality
Is this a genuinely new idea or a novel application of the technology? Does it demonstrate insight into what makes agentic systems different from traditional apps?




Resources


Tools and Technologies
CockroachDB
AWS
About the Sponsors
FAQ
 
CockroachDB
CockroachDB Cloud — Start Free — Spin up a free cluster in minutes. No credit card required.
Managed MCP Server Quickstart — Log into Cloud Console → select your cluster → copy the MCP config snippet → paste into Claude Code, Cursor, or VS Code.
ccloud CLI Documentation — Install, authenticate with a service account, and start driving infrastructure from your terminal.
CockroachDB Agent Skills Repo (GitHub) — Open-source, machine-executable skills for onboarding, operations, performance, security, and observability.
pgvector + CockroachDB (Distributed Vector Search) — Integrated vector indexing for semantic search and RAG at scale.
LangChain × CockroachDB — Provider, Vector Store, and Chat Message History integrations.
 
AWS
AWS Free Tier — Hands-on experience with AWS services at no cost.
 

About the Sponsors
CockroachDB
CockroachDB is a globally distributed operational database platform built to support the full lifecycle of AI-driven applications, from early prototypes to production systems and autonomous agents. It is no longer just an architectural preference, it is a necessity.

CockroachDB serves as the system of record for agentic memory, giving AI agents a single, resilient place to persist state, context, embeddings, and structured data. Built on an always-on architecture trusted by companies like OpenAI (ChatGPT), UiPath, CoreWeave, and Automation Anywhere, it unifies transactional and semantic workloads in one system. Fully PostgreSQL-compatible, with elastic serverless scaling and enterprise-grade security at every layer, CockroachDB enables AI agents to evolve from deterministic SQL-based tasks to semantic reasoning and long-running workflows without sacrificing context, consistency, or control.

Amazon Web Services (AWS)
AWS is the world's most comprehensive and broadly adopted cloud platform, offering over 200 fully featured services from data centers globally. With Amazon Bedrock, AWS makes it easy for developers to build and scale generative AI applications using foundation models from Anthropic, Meta, Amazon, and more with the security, compliance, and scalability that enterprises require.

 

Support
Join the Cockroach Labs Slack


 
FAQ
Do I need to pay to use CockroachDB?
No. CockroachDB Cloud has a free tier that is fully eligible for this hackathon. You can spin up a cluster in minutes at cockroachlabs.cloud with no credit card required.

Can I use other AI models besides Claude?
Yes. The CockroachDB MCP Server supports any MCP-compatible client, and the Agent Skills Repo is model-agnostic, it works with Claude, Cursor, LangChain, or your own agent framework. You must use at least one AWS service, but you can use any combination of models.

What if I'm new to CockroachDB?
Perfect. The hackathon starter kits are designed to get you from zero to a running agent in under 30 minutes. CockroachDB is fully PostgreSQL-compatible, so if you know Postgres, you already know most of CockroachDB.

Can I use CockroachDB for the vector/embedding store and the transactional store?
Yes, and this is one of CockroachDB's key differentiators for agentic workloads. CockroachDB's integrated pgvector support with distributed indexing means you can store embeddings and transactional data in one system, eliminating ETL complexity and consistency issues between a separate vector store and your operational database.

What is the Model Context Protocol (MCP)?
MCP is an open standard created by Anthropic that allows AI agents to safely and predictably interact with external systems: tools, databases, APIs, through a structured, auditable interface. CockroachDB's Managed MCP Server implements this protocol to give AI coding agents like Claude Code and Cursor a direct, secure connection to your database cluster.

What are Agent Skills?
Agent Skills are structured, machine-executable capabilities published in CockroachDB's open-source skills repository. Each skill encodes a specific CockroachDB workflow like 'profile statement fingerprints' or 'detect schema anti-patterns'  with clear inputs, outputs, and behavior. Skills follow open, standard interfaces so they work across models and agent frameworks without rewriting integrations. Think of them as reusable building blocks for production-grade database operations.




Rules

CockroachDB × AWS Hackathon – Build the Future of Agentic Memory (the “Hackathon”) Official Rules
NO PURCHASE OR PAYMENT NECESSARY TO ENTER OR WIN. A PURCHASE OR PAYMENT WILL NOT INCREASE YOUR CHANCES OF WINNING. 

SUBMISSION OF ANY ENTRY CONSTITUTES AGREEMENT TO THESE OFFICIAL RULES AS A CONTRACT BETWEEN ENTRANT (AND EACH INDIVIDUAL MEMBER OF ENTRANT), THE HACKATHON SPONSOR, AND DEVPOST.

 

1. Dates and Timing
Submission Period: June 30, 2026 (10:00 am Eastern Time) – August 18, 2026 (5:00 pm Eastern Time) (“Submission Period”).

Judging Period: August 19, 2026(10:00 am Eastern Time) – September 15, 2026 (5:00 pm Eastern Time) (“Judging Period”).

Winners Announced: On or around September 21, 2026 (3:00 pm Eastern Time).

 

2. Sponsor and Administrator
Sponsor: Cockroach Labs 125 w 25th st 11th floor, NYC, NY 10001, United States

Administrator: Devpost, Inc. (“Devpost”), 250 Broadway, Floor 24, New York, NY 10007

 

3. Eligibility
The Hackathon IS open to: 

Individuals who are at least 18 years old (or have reached the age of majority in their jurisdiction of residence at the time of entry) (“Eligible Individuals”)
Teams of up to 5 individuals (“Teams”); and
Organizations (including corporations, not-for-profit corporations and other nonprofit organizations, limited liability companies, partnerships, and other legal entities) that exist and have been organized or incorporated at the time of entry.
(the above are collectively, “Entrants”)

An Eligible Individual may join more than one Team or Organization and an Eligible Individual who is part of a Team or Organization may also enter the Hackathon on an individual basis. If a Team or Organization is entering the Hackathon, they must appoint and authorize one individual (the “Representative”) to represent, act, and enter a Submission, on their behalf. By entering a Submission on behalf of a Team or Organization you represent and warrant that you are the Representative authorized to act on behalf of your Team or Organization.

The Hackathon IS NOT open to: 

Individuals who are residents of, or Organizations domiciled in, a country, state, province or territory where the laws of the United States or local law prohibits participating or receiving a prize in the Hackathon (including, but not limited to, Brazil, Quebec, Russia, Crimea, Cuba, Iran, and North Korea and any other country designated by the United States Treasury's Office of Foreign Assets Control) 
Organizations involved with the design, production, paid promotion, execution, or distribution of the Hackathon, including the Sponsor and Administrator (“Promotion Entities”).
Employees, representatives and agents** of such Promotion Entities, and all members of their immediate family or household*  
Any other individual involved with the design, production, promotion, execution, or distribution of the Hackathon, and each member of their immediate family or household*
Any Judge (defined below), or company or individual that employs a Judge
Any parent company, subsidiary, or other affiliate*** of any organization described above
Any other individual or organization whose participation in the Hackathon would create, in the sole discretion of the Sponsor and/or Administrator, a real or apparent conflict of interest 
*The members of an individual’s immediate family include the individual’s spouse, children and stepchildren, parents and stepparents, and siblings and stepsiblings. The members of an individual’s household include any other person that shares the same residence as the individual for at least three (3) months out of the year. 

**Agents include individuals or organizations that in creating a Submission to the Hackathon, are acting on behalf of, and at the direction of, a Promotion Entity through a contractual or similar relationship.

***An affiliate is: (a) an organization that is under common control, sharing a common majority or controlling owner, or common management; or (b) an organization that has a substantial ownership in, or is substantially owned by the other organization.

 

4. How To Enter 
Entrants may enter by visiting cockroachdb-ai.devpost.com (“Hackathon Website”) and following the below steps:

Register for the Hackathon on the Hackathon Website by clicking the “Join Hackathon” button. To complete registration, sign up to create a free Devpost account, or log in with an existing Devpost account. This will enable you to receive important updates and to create your Submission. Participants must agree to the Devpost Terms of Service and the AWS Event Terms and Conditions
Entrants will obtain access to the required developer tools/platform and complete a Project described below in Project Requirements. Use of the developer tools will be subject to the license agreement related thereto. Entry in the Hackathon constitutes consent for the Sponsor and Devpost to collect and maintain an entrant’s personal information for the purpose of operating and publicizing the Hackathon.
To create an account for CockroachDB:  Visit cockroachlabs.cloud and click Sign up. Free-tier offerings, eligibility, and usage limits are governed by Cockroach Labs and may change. Entrants are responsible for reviewing the current CockroachDB Cloud terms and for any usage that exceeds free-tier limits.
To create an account for AWS Free Tier: Go to AWS Free Tier.
Free Tier offerings, eligibility, and usage limits are governed by AWS and may change. Entrants are responsible for reviewing the current AWS Free Tier terms and for any usage that exceeds Free Tier limits.
Complete and enter all of the required fields on the “Enter a Submission” page of the Hackathon Website (each a “Submission”) during the Submission Period and follow the requirements below.
 

Project Requirements`

What to Create: Entrants must build an agentic application that uses CockroachDB as its persistent memory layer, deployed on AWS. (each a “Project”). 
All required CockroachDB and AWS components must be meaningfully integrated — not just initialized within the Project.
Your Project MUST use at least 2 of the following CockroachDB Tools: 
CockroachDB Cloud Managed MCP Server — Connect AI agents directly to CockroachDB clusters with a single config snippet from the Cloud Console. Works natively with Claude Code, Cursor, and VS Code. Safe by default: read-only mode, full audit logging, zero custom proxy required. Endpoint: https://cockroachlabs.cloud/mcp
CockroachDB Distributed Vector Indexing — Store and query embeddings at scale using CockroachDB's vector support with distributed indexing. Semantic search and retrieval stay fast as your data grows — no separate vector store to maintain, no reindexing pain, and no consistency gaps between your vector data and your operational database. Ideal for RAG pipelines, long-term agent memory, and semantic search applications.
ccloud CLI (Agent-Ready) — Give your agent direct, secure access to the full CockroachDB Cloud control plane. Provision clusters, manage backups, configure networking, monitor audit logs — all from the terminal. Designed for AI with consistent noun-verb patterns, JSON output on every command, and granular service-account-based RBAC.
CockroachDB Agent Skills Repo (Open Source) — A curated, open-source collection of machine-executable Agent Skills encoding CockroachDB expertise. Skills span onboarding, query/schema design, operations, performance, security, and observability. Portable across Claude, Cursor, LangChain, and any MCP-compatible client.
Your Project MUST use at least 1 of these AWS Services: 
Amazon Bedrock (foundation models, knowledge bases, or agents)
AWS Lambda (serverless agent execution)
Amazon ECS / EKS (containerized agent workloads)
Amazon S3 (artifact or document storage)
Amazon SageMaker (model training or inference)
Amazon Bedrock Agents (multi-step agentic workflows)
Any other AWS service that powers your agent's environment
Functionality: The Project must be capable of being successfully installed and running consistently on the platform for which it is intended and must function as depicted in the video and/or expressed in the text description.
Platforms: A submitted Project must run on the platform for which it is intended and which is specified in the Submission Requirements. 
New Projects Only: Projects must be newly created by the Entrant during the Submission Period. Participants may use standard development tools, including frameworks, libraries, starter templates, and AI coding assistants, but must disclose any other pre-existing code or work incorporated into the Project. The work described and submitted must have been built during the Submission Period.
Third Party Integrations: If a Project integrates any third-party SDK, APIs and/or data, Entrant must be authorized to use them in accordance with any terms and conditions or licensing requirements of the tool.
 

Submission Requirements 

Submissions to the Hackathon must meet the following requirements:

Include a Project built with the required developer tools and meets the above Project Requirements.
Provide a URL to your code repository for judging and testing. The repository must contain all necessary source code, clear README documentation, any required dependencies, example configurations or datasets if applicable, and setup and run instructions required for the project to be functional. The repository must be public and open source by including an open source license file (we recommend MIT or Apache 2.0). This license should be detectable and visible at the top of the repository page (in the About section). 
Provide a URL to your functional demo app.
Include a text description that should explain the features and functionality of your Project.
Include a demonstration video of your Project. The video portion of the Submission:
should be less than three (3) minutes. Judges are not required to watch beyond three minutes 
must include footage that shows the Project functioning on the device for which it was built
must include footage showing the CockroachDB memory layer at work
must be uploaded to and made publicly visible on YouTube or Vimeo and a link to the video must be provided on the submission form on the Hackathon Website; and
must not include third party trademarks, or copyrighted music or other material unless the Entrant has permission to use such material.
Identify which CockroachDB tools you used (MCP Server, ccloud CLI, Distributed Vector Indexing, Agent Skills) and how — what did the agent actually do with them?
Identify which AWS Services tools you used (Amazon Bedrock, AWS Lambda, Amazon S3, etc.) and how.
Optional: Include an architectural diagram showing how CockroachDB, AWS services, and your agent interact.
Optional: Provide feedback on the CockroachDB AI tools or features.
 

Multiple Submissions 

An Entrant may submit more than one Submission, however, each Submission must be unique and substantially different from each of the Entrant’s other Submissions, as determined by the Sponsor and Devpost in their sole discretion.

Submission ownership

Be the original work of the Entrant, be solely owned by the Entrant, and not violate the IP rights of any other person or entity.

Testing 

Access must be provided to an Entrant’s working Project for judging and testing by providing a link to a website, functioning demo, or a test build. If Entrant’s website is private, Entrant must include login credentials in its testing instructions. The Entrant must make the Project available free of charge and without any restriction, for testing, evaluation and use by the Sponsor, Administrator and Judges until the Judging Period ends. Judges are not required to test the Project and may choose to judge based solely on the text description, images, and video provided in the Submission.

If the Project includes software that runs on proprietary or third party hardware that is not widely available to the public, including software running on devices or wearable technology other than smartphones, tablets, or desktop computers, the Sponsor and/or Administrator reserve the right, at their sole discretion, to require the Entrant to provide physical access to the Project hardware upon request.  

Language Requirements

All Submission materials must be in English or, if not in English, the Entrant must provide an English translation of the demonstration video, text description, and testing instructions as well as all other materials submitted. 

Team Representation

If a team or organization is entering the Hackathon, they must appoint and authorize one individual (the “Representative”) to represent, act, and enter a Submission, on their behalf. The Representative must meet the eligibility requirements above. By entering a Submission on the Hackathon Website on behalf of a team or organization you represent and warrant that you are the Representative authorized to act on behalf of your team or organization.

Intellectual Property 

Your Submission must: (a) be your (or your Team, or Organization’s) original work product; (b) be solely owned by you, your Team, your Organization with no other person or entity having any right or interest in it; and (c) not violate the intellectual property rights or other rights including but not limited to copyright, trademark, patent, contract, and/or privacy rights, of any other person or entity. An Entrant may contract with a third party for technical assistance to create the Submission provided the Submission components are solely the Entrant’s work product and the result of the Entrant’s ideas and creativity, and the Entrant owns all rights to them. An Entrant may submit a Submission that includes the use of open source software or hardware, provided the Entrant complies with applicable open source licenses and, as part of the Submission, creates software that enhances and builds upon the features and functionality included in the underlying open source product. By entering the Hackathon, you represent, warrant, and agree that your Submission meets these requirements.

Financial or Preferential Support 

A Project must not have been developed, or derived from a Project developed, with financial or preferential support from the Sponsor or Administrator. Such Projects include, but are not limited to, those that received funding or investment for their development, were developed under contract, or received a commercial license, from the Sponsor or Administrator any time prior to the end of Hackathon Submission Period. The Sponsor, at their sole discretion, may disqualify a Project, if awarding a prize to the Project would create a real or apparent conflict of interest.

 

5. Submission Modifications
Draft Submissions 

Prior to the end of the Submission Period, you may save draft versions of your submission on Devpost to your portfolio before submitting the Submission materials to the Hackathon for evaluation. Once the Submission Period has ended, you may not make any changes or alterations to your Submission, but you may continue to update the Project in your Devpost portfolio.

Modifications After the Submission Period

The Sponsor and Devpost may permit you to modify part of your Submission after the Submission Period for the purpose of adding, removing or replacing material that potentially infringes a third party mark or right, discloses personally identifiable information, or is otherwise inappropriate. The modified Submission must remain substantively the same as the original Submission with the only modification being what the Sponsor and Devpost permits. 

 

6. Judges & Criteria
Sponsor and Administrator reserve the sole right to determine the eligibility and judging methodologies for all submissions. This process may utilize expert panels, peer review, automated AI-driven analysis, or any combination thereof to ensure efficient, fair, and objective evaluation. Eligible submissions will be evaluated by a panel of judges selected by the Sponsor (the “Judges”). Judges may be employees of the sponsor or third parties, may or may not be listed individually on the Hackathon Website, and may change before or during the Judging Period. Judging may take place in one or more rounds with one or more panels of Judges, at the discretion of the sponsor. 

Stage One) The first stage will determine via pass/fail whether the ideas meet a baseline level of viability, in that the Project reasonably fits the theme and reasonably applies the required APIs/SDKs featured in the Hackathon.

Stage Two) All Submissions that pass Stage One will be evaluated in Stage Two based on the following equally weighted criteria (the “Judging Criteria”):

Entries will be judged on the following equally weighted criteria, and according to the sole and absolute discretion of the judges:

Agentic Memory Design
Does CockroachDB play a meaningful, production-grade role as the agent's memory layer? Is it used for more than toy queries — state, embeddings, context, or transactional data at real scale?
Technological Implementation
Is the integration with CockroachDB tools (distributed vector index, MCP Server, ccloud CLI) quality software engineering? Does the agent use the tools correctly and safely?
Real-World  Impact
How big of an impact could the project have on real users or workflows? Is the use case meaningful, not just technically impressive?
Product Readiness
Is the design secure, observable, and scalable? Has the team thought about resilience, access control, and what happens when things go wrong?
Creativity & Originality
Is this a genuinely new idea or a novel application of the technology? Does it demonstrate insight into what makes agentic systems different from traditional apps?
The scores from the Judges will determine the potential winners of the applicable prizes. The Entrant(s) that are eligible for a Prize, and whose Submissions earn the highest overall scores based on the applicable Judging Criteria, will become potential winners of that Prize.

Tie Breaking 

For each Prize listed below, if two or more Submissions are tied, the tied Submission with the highest score in the first applicable criterion listed above will be considered the higher scoring Submission. In the event any ties remain, this process will be repeated, as needed, by comparing the tied Submissions’ scores on the next applicable criterion. If two or more Submissions are tied on all applicable criteria, the panel of Judges will vote on the tied Submissions.

 

7. Intellectual Property Rights
All Submissions remain the intellectual property of the individuals or organizations that developed them. By submitting an entry, entrants agree that the Sponsor will have a non-exclusive license to use such entry for judging the entry. Entrants agree that the sponsor and Devpost shall have the right to promote the Submission and use the name, likeness, voice and image of all individuals contributing to a Submission, in any materials promoting or publicizing the Hackathon and its results, during the Hackathon Period and for three years thereafter.  Some Submission components may be displayed to the public. Other Submission materials may be viewed by the sponsor, Devpost, and judges for screening and evaluation. By submitting an entry or accepting any prize, entrants represent and warrant that (a) submitted content is not copyrighted, protected by trade secret or otherwise subject to third party intellectual property rights or other proprietary rights, including privacy and publicity rights, unless entrant is the owner of such rights or has permission from their rightful owner to post the content; and (b) the content submitted does not contain any viruses, Trojan horses, worms, spyware or other disabling devices or harmful or malicious code.

 

8. Prizes
Winner

Prize

Qty

Eligible Submissions 

Judging Criteria

1st Place

$5,000 in USD
Social Blog feature
1

All Eligible Submissions

1st Place

2nd Place

$2,500 in USD
Social Blog feature
1

All Eligible Submissions

2nd Place

3rd Place

$1,250 in USD
Social Blog feature
1

All Eligible Submissions

3rd Place

IMPORTANT NOTES ON MULTIPLE PRIZE ELIGIBILITY:

A project can only win one (1) prize.
If there are no eligible submissions for a prize, that prize will not be awarded.
 

Substitutions & Changes: Prizes are non-transferable by the winner. Sponsor in its sole discretion has the right to make a prize substitution of equivalent or greater value. Sponsor will not award a prize if there are no eligible Submissions entered in the Hackathon, or if there are no eligible Entrants or Submissions for a specific prize.
Verification Requirement: THE AWARD OF A PRIZE TO A POTENTIAL WINNER IS SUBJECT TO VERIFICATION OF THE IDENTITY, QUALIFICATIONS AND ROLE OF THE POTENTIAL WINNER IN THE CREATION OF THE SUBMISSION. No Submission or Entrant shall be deemed a winning Submission or winner until their post-competition prize affidavits have been completed and verified, even if prospective winners have been announced verbally or on the competition website. The final decision to designate a winner shall be made by the Sponsor and/or Administrator. 
Prize Delivery: Prizes will be payable to the Entrant, if an individual; to the Entrant’s Representative, if a Team; or to the Organization, if the Entrant is an Organization. It will be the responsibility of the winning Entrant’s Representative to allocate the Prize among their Team or Organization’s participating members, as the Representative deems appropriate. A monetary Prize will be mailed to the winning Entrant’s address (if an individual) or the Representative’s address (if a Team or Organization), or sent electronically to the Entrant, Entrant’s Representative, or Organization’s bank account, only after receipt of the completed winner affidavit and other required forms (collectively the “Required Forms”), if applicable. The deadline for returning the Required Forms to the Administrator is ten (10) business days after the Required Forms are sent. Failure to provide correct information on the Required Forms, or other correct information required for the delivery of a Prize, may result in delayed Prize delivery, disqualification of the Entrant, or forfeiture of a Prize. Prizes will be delivered within 60 days of the Sponsor or Devpost’s receipt of the completed Required Forms.
Fees & Taxes: Winners (and in the case of Team or Organization, all participating members) are responsible for any fees associated with receiving or using a prize, including but not limited to, wiring fees or currency exchange fees. Winners (and in the case of Team or Organization, all participating members) are responsible for reporting and paying all applicable taxes in their jurisdiction of residence (federal, state/provincial/territorial and local). Winners may be required to provide certain information to facilitate receipt of the award, including completing and submitting any tax or other forms necessary for compliance with applicable withholding and reporting requirements. United States residents may be required to provide a completed form W-9 and residents of other countries may be required to provide a completed W-8BEN form. Winners are also responsible for complying with foreign exchange and banking regulations in their respective jurisdictions and reporting the receipt of the Prize to relevant government departments/agencies, if necessary. The Sponsor, Devpost, and/or Prize provider reserves the right to withhold a portion of the prize amount to comply with the tax laws of the United States or other Sponsor jurisdiction, or those of a winner’s jurisdiction.
 

9. Entry Conditions and Release
By entering the Hackathon, you (and, if you are entering on behalf of a Team, Organization each participating members) agree(s) to the following:
The relationship between you, the Entrant, and the Sponsor and Administrator, is not a confidential, fiduciary, or other special relationship.
You will be bound by and comply with these Official Rules and the decisions of the Sponsor, Administrator, and/or the Hackathon Judges which are binding and final in all matters relating to the Hackathon.
You release, indemnify, defend and hold harmless the Promotion Entities, and their respective parent, subsidiary, and affiliated companies, the Prize suppliers and any other organizations responsible for sponsoring, fulfilling, administering, advertising or promoting the Hackathon, and all of their respective past and present officers, directors, employees, agents and representatives (hereafter the “Released Parties”) from and against any and all claims, expenses, and liabilities (including reasonable attorneys’ fees), including but not limited to negligence and damages of any kind to persons and property, defamation, slander, libel, violation of right of publicity, infringement of trademark, copyright or other intellectual property rights, property damage, or death or personal injury arising out of or relating to a Entrant’s entry, creation of Submission or entry of a Submission, participation in the Hackathon, acceptance or use or misuse of the Prize (including any travel or activity related thereto) and/or the broadcast, transmission, performance, exploitation or use of the Submission as authorized or licensed by these Official Rules. 
Without limiting the foregoing, the Released Parties shall have no liability in connection with: 
Any incorrect or inaccurate information, whether caused by the Sponsor or Administrator’s electronic or printing error, or by any of the equipment or programming associated with or utilized in the Hackathon; 
Technical failures of any kind, including, but not limited to malfunctions, interruptions, or disconnections in phone lines, internet connectivity or electronic transmission errors, or network hardware or software or failure of the Hackathon Website;
Unauthorized human intervention in any part of the entry process or the Hackathon; 
Technical or human error which may occur in the administration of the Hackathon or the processing of Submissions; or 
Any injury or damage to persons or property which may be caused, directly or indirectly, in whole or in part, from the Entrant’s participation in the Hackathon or receipt or use or misuse of any Prize.
The Released Parties are not responsible for incomplete, late, misdirected, damaged, lost, illegible, or incomprehensible Submissions or for address or email address changes of the Entrants. Proof of sending or submitting the aforementioned will not be deemed to be proof of receipt by the Sponsor or Administrator. If for any reason any Entrant’s Submission is determined to have not been received or been erroneously deleted, lost, or otherwise destroyed or corrupted, the Entrant’s sole remedy is to request the opportunity to resubmit its Submission. Such a request must be made promptly after the Entrant knows or should have known there was a problem and will be determined at the sole discretion of the Sponsor.

 

10. Publicity
By participating in the Hackathon, Entrant consents to the promotion and display of the Entrant’s Submission, and to the use of personal information about themselves for promotional purposes, by the Sponsor, Administrator, and third parties acting on their behalf. Such personal information includes, but is not limited to, your name, likeness, photograph, voice, opinions, comments and hometown and country of residence. It may be used in any existing or newly created media, worldwide without further payment or consideration or right of review, unless prohibited by law. Authorized use includes but is not limited to advertising and promotional purposes. 

 

11. General Conditions 
Sponsor and Administrator reserve the right, in their sole discretion, to cancel, suspend and/or modify the Hackathon, or any part of it, in the event of a technical failure, fraud, or any other factor or event that was not anticipated or is not within their control.
Sponsor and Administrator reserve the right in their sole discretion to disqualify any individual or Entrant if it finds to be actually or presenting the appearance of tampering with the entry process or the operation of the Hackathon or to be acting in violation of these Official Rules or in a manner that is inappropriate, unsportsmanlike, not in the best interests of this Hackathon, or a violation of any applicable law or regulation.
Any attempt by any person to undermine the proper conduct of the Hackathon may be a violation of criminal and civil law. Should the Sponsor or Administrator suspect that such an attempt has been made or is threatened, they reserve the right to take appropriate action including but not limited to requiring an Entrant to cooperate with an investigation and referral to criminal and civil law enforcement authorities.
If there is any discrepancy or inconsistency between the terms and conditions of the Official Rules and disclosures or other statements contained in any Hackathon materials, including but not limited to the Hackathon Submission form, Hackathon Website, or advertising, the terms and conditions of the Official Rules shall prevail.
The terms and conditions of the Official Rules are subject to change at any time, including the rights or obligations of the Entrant, the Sponsor and Administrator. The Sponsor and Administrator will post the terms and conditions of the amended Official Rules on the Hackathon Website. To the fullest extent permitted by law, any amendment will become effective at the time specified in the posting of the amended Official Rules or, if no time is specified, the time of posting.
If at any time prior to the deadline, an Entrant or prospective Entrant believes that any term in the Official Rules is or may be ambiguous, they must submit a written request for clarification. 
The Sponsor or Administrator’s failure to enforce any term of these Official Rules shall not constitute a waiver of that provision. Should any provision of these Official Rules be or become illegal or unenforceable in any jurisdiction whose laws or regulations may apply to an Entrant, such illegality or unenforceability shall leave the remainder of these Official Rules, including the Rule affected, to the fullest extent permitted by law, unaffected and valid. The illegal or unenforceable provision shall be replaced by a valid and enforceable provision that comes closest and best reflects the Sponsor’s intention in a legal and enforceable manner with respect to the invalid or unenforceable provision.
Excluding Submissions, all intellectual property related to this Hackathon, including but not limited to copyrighted material, trademarks, trade-names, logos, designs, promotional materials, web pages, source codes, drawings, illustrations, slogans and representations are owned or used under license by the Sponsor and/or Administrator. All rights are reserved. Unauthorized copying or use of any copyrighted material or intellectual property without the express written consent of its owners is strictly prohibited. Any use in a Submission of Sponsor or Administrator’s intellectual property shall be solely to the extent provided for in these Official Rules.
 

12. Limitations of Liability
By entering, all Entrants (including, in the case of a Team or Organization, all participating members) agree to release the Released Parties from any and all liability in connection with the Prizes or Entrant’s participation in the Hackathon. Provided, however, that any liability limitation regarding gross negligence or intentional acts, or events of death or body injury shall not be applicable in jurisdictions where such limitation is not legal.

 

13. Disputes
Except where prohibited by law, as a condition of participating in this Hackathon, Entrant agrees that:
Any and all disputes and causes of action arising out of or connected with this Hackathon, or any Prizes awarded, shall be resolved individually, without resort to any form of class action lawsuit, and exclusively by final and binding arbitration under the rules of the American Arbitration Association and held at the AAA regional office nearest the contestant;
The Federal Arbitration Act shall govern the interpretation, enforcement and all proceedings at such arbitration; and
Judgment upon such arbitration award may be entered in any court having jurisdiction.
Under no circumstances will Entrant be permitted to obtain awards for, and Entrant hereby waives all rights to claim, punitive, incidental or consequential damages, or any other damages, including attorneys’ fees, other than contestant’s actual out-of-pocket expenses (i.e., costs associated with entering this Hackathon), and Entrant further waives all rights to have damages multiplied or increased.
All issues and questions concerning the construction, validity, interpretation and enforceability of these Official Rules, or the rights and obligations of the Entrant and Sponsor in connection with this Hackathon, shall be governed by, and construed in accordance with, the substantive laws of the State of New York, USA without regard to New York choice of law rules.
SOME JURISDICTIONS DO NOT ALLOW THE LIMITATIONS OR EXCLUSION OF LIABILITY FOR INCIDENTAL OR CONSEQUENTIAL DAMAGES, SO THE ABOVE LIMITATIONS OF LIABILITY MAY NOT APPLY TO YOU.