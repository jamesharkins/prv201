# Terms of use for Differential deployments

The source code in this repository is released under the MIT License (`LICENSE`). These
terms are separate: they are the conditions under which the team would offer a running
Differential to a repair business, and they are what the milestone documents mean by "terms
of use". They do not restrict the code license, and anyone who builds the code themselves
takes on the responsibilities below without the team's involvement.

## Who may use it

1. Differential is offered to repair businesses for use by qualified persons: people with the
   training, skill and knowledge to test and repair the equipment on the bench and to avoid
   its electrical hazards (the sense of 29 CFR 1910.399). The business confirms that every
   user meets that standard. This applies to sole proprietors too, although the OSH Act
   covers only employers (29 CFR 1904.31(b)(1)).
2. Trainees use trainee mode, and a named supervisor is required before any step on a unit
   with a high-voltage supply.
3. Consumers and hobbyists are not served.

## What it may not be used for

4. Rating, ranking, monitoring, disciplining or setting the pay of staff. Tickets record roles
   and the job, not a person's performance, and they may not be used to evaluate a technician
   or a trainee. Tickets stay in the business's system; the technician who signs one may
   export it.
5. Work on the mains side of a unit (plug, fuse holder, power switch, mains wiring, primary
   of the power transformer). Differential refuses these steps.
6. Unattended probing, or any use in which a person does not choose, take and confirm every
   measurement.
7. Relying on the hazard map of a circuit model that has not been checked against the
   manual's voltage chart. Until it is, Differential treats every test point of a unit with
   a high-voltage supply as high voltage.

## What the business keeps and answers for

8. Circuit models transcribed from service manuals stay with the business that holds the
   manuals; the team ships none.
9. The business answers for its circuit models and its staff; the technician answers for the
   measurements and the precautions taken; the team answers for the hazard map, the stated
   performance and corrections (M1, Part 4).
10. Photos and complaints stay on the business's machine in offline mode. In live mode,
    complaint text and photos (with metadata removed) are sent to the model provider under
    its terms.

## Safety records

11. How a unit was first powered, the owner's approval to remove parts, discharge readings
    and a trainee's supervisor are recorded only by the technician in the application's
    forms. The chat and the language model cannot record them.

## Performance claims and corrections

12. The team quotes only results measured under the locked targets, each labelled as
    simulated or measured on hardware, with its interval; no accuracy claim about real
    equipment is made before the hardware results exist.
13. A business that finds a wrong hazard warning, a missing lock or a wrong recommendation
    reports it to the team; the team corrects the hazard map or code, versions the change and
    tells every business using the affected circuit model.

## Changes

The team states each release's measured performance and known limits with the release, and
records changes in `CHANGELOG.md`.
