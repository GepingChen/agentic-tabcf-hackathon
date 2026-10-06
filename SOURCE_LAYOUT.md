# Readable source export

Root src/ and pyproject.toml are the Apache-2.0 thin entry. Runtime files
and configs were copied unchanged from the accepted entry wheel.
vendor/dcfa/ contains the installable MIT parent source from parent_source.tar
at parent_commit.txt; Python source and package assets are unchanged.
Historical documentation links were adapted to this focused export.
The original accepted wheels and dependency lock remain the default install
path. To rebuild locally: python -m pip wheel --no-deps ./vendor/dcfa .

TabCF's original separate source archive is retained in the local v6 ZIP.
The managed API entry executes the bundled DCFA adapter and does not import
that separate source tree. Its MIT license and recorded commit remain here.
No licenses were changed. Code outside the entry's permitted tool surface
is not exposed by agentic-tabcf.

Included example results are the original public cigarette development run.
The offline HTML is a presentation derivative; neither export refits models.
The full comparison, historical source archives and installation logs remain
in the separate local ZIP rather than this focused source repository.

Root Apache-2.0 applies to the entry/new documentation. MIT dependencies
and source data terms are disclosed in LICENSING.md and NOTICE.
Repository publication and official contest submission are separate.
