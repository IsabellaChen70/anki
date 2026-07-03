# Vantage (MCAT readiness, built on Anki)

**Exam: MCAT** (Medical College Admission Test), scored 472 to 528 across four sections (Chem/Phys, CARS, Bio/Biochem, Psych/Soc), each 118 to 132.

Vantage is a desktop and Android study app built on this Anki fork. It keeps Anki's FSRS spaced repetition, adds a topic-interleaving review order in the shared Rust core, and adds an honest readiness layer: three separate scores (memory, performance, readiness), each with a range and a give-up rule that shows no number when the evidence is thin. See **[VANTAGE.md](./VANTAGE.md)** for the project overview, the three repositories, and build and run instructions.

![Vantage dashboard: three separate scores with ranges, exam coverage, and the best next topic](docs/img/dashboard.png)

**Reviewing this?** Start with the 5-minute tour in [VANTAGE.md](./VANTAGE.md#for-reviewers-a-5-minute-tour). All test and benchmark evidence is collected in one place at [vantage_tools/TEST_RESULTS.md](vantage_tools/TEST_RESULTS.md), and the Rust engine change is written up in [RUST_CHANGE_NOTE.md](RUST_CHANGE_NOTE.md).

**Download and run (no build):** desktop `.dmg` + add-on from the [latest release](https://github.com/IsabellaChen70/anki/releases/latest); Android `.apk` from the [Android release](https://github.com/IsabellaChen70/Anki-Android/releases/latest).

The rest of this file is the upstream Anki README.

---

# Anki

[![Build Status](https://github.com/ankitects/anki/actions/workflows/ci.yml/badge.svg)](https://github.com/ankitects/anki/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-dev--docs.ankiweb.net-blue)](https://dev-docs.ankiweb.net)

This repo contains the source code for the computer version of
[Anki](https://apps.ankiweb.net).

# About

Anki is a spaced repetition program. Please see the [website](https://apps.ankiweb.net) to learn more.

This repo contains the source code for the computer version of
[Anki](https://apps.ankiweb.net).

## Getting Started

### Contributing

Want to contribute to Anki? Check out the [Contribution Guidelines](./docs/contributing.md).

For more information on building and developing, please see [Development](./docs/development.md).

#### Contributors

The following people have contributed to Anki: [CONTRIBUTORS](./CONTRIBUTORS)

### Anki Betas

If you'd like to try development builds of Anki but don't feel comfortable
building the code, please see [Anki betas](https://betas.ankiweb.net/).

## License

Anki's license: [LICENSE](./LICENSE)
