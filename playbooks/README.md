# Playbooks

Playbooks describe recurring mission shapes that Battalion can assess deterministically.

The current packaged playbook catalog is:

```text
battalion/playbooks.yml
```

It remains inside the Python package so installed CLI execution can load it reliably. This top-level directory documents the product concept and reserves the future external playbook surface.

This directory is architectural intent, not a current runtime catalog path or package boundary.

## Doctrine

Playbooks help Battalion understand mission scope. They must not turn Assessment into project-wide architecture review.

Good playbooks:

- identify mission domains;
- ask only mission-relevant questions;
- produce planning-ready understanding;
- preserve deterministic behavior.

Poor playbooks:

- invent deployment requirements;
- force framework selection when irrelevant;
- add architecture assumptions outside the mission;
- recommend implementation before planning.
