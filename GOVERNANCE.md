# WikidPad Project Governance

## Overview

WikidPad is a single-user, open-source desktop wiki application.
This governance document establishes the framework that guides the
project's development and direction.

## Core Principle

**Sustainability**: The project's primary focus is ensuring long-term
  viability and maintenance. Decisions are made by active contributors
  and maintainers to keep WikidPad stable, performant, and relevant.
**Effective Use of Contributor Ressources**: Given limited maintainer
  and contributor capacity, we prioritize efficient decision-making by
  those actively contributing code and effort.

## Project Structure

### Roles and Responsibilities

#### Project Maintainers
- Issue triage, and pull request reviews
- Have admin/maintain permissions on the repository
- Set technical standards and enforce code quality
- Make strategic decisions on project direction
- Lead development of features and maintenance tasks
- Typically active contributors with demonstrated commitment

#### Contributors
- Develop features, fix bugs, improve documentation
- Participate in code reviews
- Have push/pull request permissions subject to review
- May operate independently on assigned areas

#### Users
- Report bugs and suggest improvements through issues
- Provide feedback through discussions

## Decision-Making Framework

### Minor Decisions (Self-Directed)
**Scope**: Small bug fixes, documentation updates,
  minor code refactoring

**Process**:
- Created as pull requests with clear descriptions
- Subject to standard code review by maintainers
- 4-week review window for feedback
- Can be merged with approval from one maintainer

### Moderate Decisions (Maintainer Review)
**Scope**: Feature enhancements, API changes, performance optimizations,
  dependency updates

**Process**:
- Pull request includes clear rationale and technical justification
- Requires review and approval from at least one maintainer
- 8-week review window for feedback
- Maintainers evaluate technical merit, user impact, and
  maintenance burden

### Major Decisions (Maintainer Consensus)
**Scope**: Major architectural changes, project direction shifts,
  governance changes, significant breaking changes

**Process**:
- Initiated as GitHub Issue or Discussion with detailed proposal
- 16-week community/maintainer discussion period
- Requires agreement among active maintainers before implementation
- Documentation of rationale and alternatives considered
- Decision made by those committing code effort

## Processes

### Issue Management
1. **Reporting**: Users report bugs and feature requests via GitHub Issues
2. **Triage**: Maintainers classify issues by type, priority, and scope
3. **Assignment**: Issues assigned to contributors with capacity
4. **Resolution**: Contributors develop fixes or features,
   submitted as pull requests

### Pull Request Workflow
1. **Submission**: Contributor creates PR with description,
   links to related issues
2. **Automated Checks**: CI/CD pipeline validates code style and tests
3. **Review**: Maintainers review and provide feedback
4. **Iteration**: Contributor addresses feedback and updates the PR
5. **Approval**: Maintainers approve when criteria are met
6. **Merge**: PR is merged to `master` branch
7. **Release**: Changes included in next scheduled release or patch

### Release Management
- Releases follow semantic versioning (MAJOR.MINOR.PATCH)
- Scheduled releases occur when sufficient changes accumulate or
  critical fixes are needed
- Release notes document new features, improvements, and fixes
- Experimental features may be marked as beta

## Rules & Norms

### Technical Standards
- Code must follow project style guidelines
  (documented in CONTRIBUTING.md)
- All commits should have clear, descriptive messages
- New features should include tests and documentation
- Breaking changes require explicit discussion and clear migration path
- Changes must not introduce new maintenance burden

### Collaboration Norms
- Provide specific, actionable feedback during reviews
- Credit contributors' work in commit messages and release notes
- Respect that maintainers are volunteers with finite capacity
- Prioritize maintainability and sustainability in technical decisions

## Resource Management & Allocation

### Contribution Pathways
- **Code Contributions**: Development, bug fixes, refactoring
- **Testing**: Cross-platform testing, validation
- **Documentation**: README, guides, API docs
- **Community Support**: Issue triage, user support

### Prioritization Criteria
1. **Sustainability**: Changes that improve maintainability and
  long-term viability
2. **Stability**: Bug fixes and performance improvements
3. **User Impact**: Features that solve real user problems
4. **Maintenance Burden**: Preference for solutions that reduce
   rather than increase load

## Setting Direction & Addressing Challenges

### Project Direction
- WikidPad remains focused on its core mission:
  a powerful, single-user desktop wiki
- Backward compatibility maintained where feasible
- Direction set by active maintainers based on technical needs
  and user feedback
- Updates communicated via release notes and README

### Key Challenges & Response
- **Limited Maintainer Capacity**: Focus on high-impact,
  sustainable improvements
- **Feature Requests**: Evaluated against scope and maintainability;
  contributions welcomed
- **Bug Reports**: Triaged by severity; critical bugs prioritized
- **Technical Debt**: Addressed incrementally as capacity allows

## Governance Evolution

This governance document is itself subject to evolution:
- **Amendments**: Changes proposed and decided by active maintainers
- **Feedback**: Input from contributors welcome via issues/discussions
- **Review**: Governance reviewed as needed to reflect project reality
- **Transparency**: Changes logged with rationale in commit history

