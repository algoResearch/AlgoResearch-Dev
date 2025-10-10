from dashboard.models import *
from dashboard.forms import *
from django.contrib.auth.decorators import user_passes_test

def clone_submission(original, user, title_prefix, progress_report=None, renewal_status=None, animal_disposition=None):
    new_submission = IACUCSubmission.objects.create(
        user=user,
        protocol_title=f"{title_prefix} {original.protocol_title}",
        principal_investigator=original.principal_investigator,
        original_submission=original,
        status='draft',
        lay_abstract=original.lay_abstract,
        benefits=original.benefits,
        experimental_summary=original.experimental_summary,
        involves_vertebrate_animals=original.involves_vertebrate_animals,
        federal_funding=original.federal_funding,
        internal_federal_funding=original.internal_federal_funding,
        private_commercial_funding=original.private_commercial_funding,
        uses_outside_tissues=original.uses_outside_tissues,
        source_assurance_number=original.source_assurance_number,
        source_protocol_number=original.source_protocol_number,
        external_collaboration=original.external_collaboration,
        off_campus_live_animal_work=original.off_campus_live_animal_work,
        housing_outside_facility_12hr=original.housing_outside_facility_12hr,
        public_area_transport=original.public_area_transport,
        field_studies=original.field_studies,
        annual_review_date=original.annual_review_date,
        triennial_review_date=original.triennial_review_date,
        adverse_events=original.adverse_events,
        alternative_to_animal_use=original.alternative_to_animal_use,
        alt_to_procedures=original.alt_to_procedures,
        duplication_prevention=original.duplication_prevention,
        future_use_plan=original.future_use_plan,
        future_use_description=original.future_use_description,
        progress_report=progress_report,
        renewal_status=renewal_status,
        animal_disposition=animal_disposition if renewal_status == "lapse" else None,
    )

    species_map = {}
        # ✅ Clone related species entries
    for species in original.species_entries.all():
            new_species = IACUCProtocolSpecies.objects.create(
                submission=new_submission,
                species_name=species.species_name,
                breeding=species.breeding or False,
                procedures=species.procedures or False,
                restraint=species.restraint or False,
                surgery=species.surgery or False,
                vet_drugs=species.vet_drugs or False,
                test_agents=species.test_agents or False,
                euthanize=species.euthanize or False,
                age_range=species.age_range or False,
                target_weight=species.target_weight or False,
                max_cages=species.max_cages,
                avg_weeks_housed=species.avg_weeks_housed,
                is_pathogen_free=species.is_pathogen_free,
                identification_methods=species.identification_methods,
                species_justification=species.species_justification,
                other_justification=species.other_justification,
            )
            species_map[species.id] = new_species
            for strain in species.speciesstrain_set.all():
                SpeciesStrain.objects.create(
                    submission=new_submission,
                    species=new_species,
                    strain=strain.strain,
                    age=strain.age,
                    weight=strain.weight,
                    phenotype=strain.phenotype
                )

            # 📍 Use Locations
            for loc in species.speciesuselocation_set.all():
                SpeciesUseLocation.objects.create(
                    submission=new_submission,
                    species=new_species,
                    location=loc.location,
                    room=loc.room,
                    location_type=loc.location_type
                )

            # 🧫 Breeding
            if hasattr(species, 'breeding_entry'):
                for entry in species.breeding_entry.all():
                    SpeciesBreeding.objects.create(
                        submission=new_submission,
                        species=new_species,
                        transgenic_flag=entry.transgenic_flag,
                        maintain_colony=entry.maintain_colony
                    )

            # 🧪 Procedures
            for proc in species.procedure_entry.all():
                SpeciesProcedure.objects.create(
                    submission=new_submission,
                    species=new_species,
                    procedure_entry=proc.procedure_entry,
                    description=proc.description
                )

            # 🪢 Restraint
            if hasattr(species, 'restraint_entry'):
                for r in species.restraint_entry.all():
                    SpeciesRestraint.objects.create(
                        submission=new_submission,
                        species=new_species,
                        restraint_type=r.restraint_type,
                        rationale=r.rationale,
                        duration=r.duration,
                        acclimation=r.acclimation
                    )

            # 🔪 Surgery
            if hasattr(species, 'surgery_entry'):
                for s in species.surgery_entry.all():
                    SpeciesSurgery.objects.create(
                        submission=new_submission,
                        species=new_species,
                        surgery_type=s.surgery_type,
                        other_surgery_description=s.other_surgery_description,
                        recovery_type=s.recovery_type,
                        pre_op_procedures=s.pre_op_procedures,
                        surgical_attire=s.surgical_attire,
                        support_anesthesia=s.support_anesthesia,
                        monitoring_plan=s.monitoring_plan,
                        suture_removal_timing=s.suture_removal_timing,
                        clinical_parameters=s.clinical_parameters,
                        analgesics_withheld=s.analgesics_withheld,
                        surgery_location_building=s.surgery_location_building,
                        surgery_location_room=s.surgery_location_room,
                        surgery_location_type=s.surgery_location_type
                    )

            # 🩹 MSS
            for mss in species.speciesmss_set.all():
                SpeciesMSS.objects.create(
                    submission=new_submission,
                    species=new_species,
                    multiple_surgeries=mss.multiple_surgeries,
                    surgery_description=mss.surgery_description
                )

            # 💊 Vet Drugs
            for drug in species.speciesvetdrug_set.all():
                SpeciesVetDrug.objects.create(
                    submission=new_submission,
                    species=new_species,
                    generic_name=drug.generic_name,
                    drug_type=drug.drug_type,
                    dose=drug.dose,
                    frequency=drug.frequency,
                    route_admin=drug.route_admin,
                    procedure_use=drug.procedure_use,
                    is_pharma_grade=drug.is_pharma_grade,
                    non_pharma_justification=drug.non_pharma_justification
                )

            # ☣️ Hazards
            for hazard in species.hazardousagent_set.all():
                HazardousAgent.objects.create(
                    submission=new_submission,
                    species=new_species,
                    category=hazard.category,
                    agent_name=hazard.agent_name,
                    committee_number=hazard.committee_number,
                    route_admin=hazard.route_admin,
                    other_route=hazard.other_route,
                    volume_frequency=hazard.volume_frequency,
                    duration=hazard.duration,
                    brought_into_facility=hazard.brought_into_facility,
                    precautions=hazard.precautions,
                    is_pharma_grade=hazard.is_pharma_grade
                )

            for euth in species.specieseuthanasia_set.all():
                SpeciesEuthanasia.objects.create(
                    submission=new_submission,
                    species=new_species,
                    method=euth.method,
                    num_b=euth.num_b,
                    num_c=euth.num_c,
                    num_d=euth.num_d,
                    num_e=euth.num_e,
                    justification=euth.justification,
                    pain_distress=euth.pain_distress,
                    pain_nature=euth.pain_nature,
                    euthanasia_criteria=euth.euthanasia_criteria,
                    requesting_exemptions=euth.requesting_exemptions,
                    exemptions_justification=euth.exemptions_justification,
                    food_water_restriction=euth.food_water_restriction,
                    restriction_justification=euth.restriction_justification,
                    special_husbandry=euth.special_husbandry,
                    husbandry_description=euth.husbandry_description,
                    reduce_description=euth.reduce_description,
                    refine_description=euth.refine_description,
                    replace_description=euth.replace_description,
                    adverse_reactions_expected=euth.adverse_reactions_expected,
                    adverse_reactions_description=euth.adverse_reactions_description
                )

            # ✅ Clone funding sources
            for source in original.funding_sources.all():
                IACUCFundingSource.objects.create(
                    submission=new_submission,
                    source=source.source,
                    grant_title=source.grant_title,
                    funded=source.funded,
                    pi_on_grant=source.pi_on_grant,
                    end_date=source.end_date
                )

            for source in original.internal_funding_sources.all():
                IACUCInternalFundingSource.objects.create(
                    submission=new_submission,
                    organization=source.organization,
                    department=source.department,
                    fund_title=source.fund_title,
                    sponsored_projects_number=source.sponsored_projects_number
                )

            for source in original.private_funding_sources.all():
                IACUCPrivateFundingSource.objects.create(
                    submission=new_submission,
                    company_name=source.company_name,
                    fund_title=source.fund_title,
                    due_date=source.due_date
                )

            # ✅ Clone housing, transport, etc.
            if hasattr(original, 'outside_housing'):
                orig = original.outside_housing
                OutsideHousing.objects.create(
                    submission=new_submission,
                    under_24hrs=orig.under_24hrs,
                    under_24hrs_location=orig.under_24hrs_location,
                    under_24hrs_justification=orig.under_24hrs_justification,
                    over_24hrs=orig.over_24hrs,
                    over_24hrs_location=orig.over_24hrs_location,
                    over_24hrs_justification=orig.over_24hrs_justification
                )

            if hasattr(original, 'public_transport'):
                orig = original.public_transport
                PublicTransportUse.objects.create(
                    submission=new_submission,
                    following_policy=orig.following_policy,
                    justification=orig.justification
                )

            if hasattr(original, 'field_study_details'):
                orig = original.field_study_details
                FieldStudyDetails.objects.create(
                    submission=new_submission,
                    location=orig.location,
                    animals_captured=orig.animals_captured
                )
            if hasattr(original, 'wildlife_capture'):
                wc = original.wildlife_capture
                WildlifeCapture.objects.create(
                    submission=new_submission,
                    equipment_used=wc.equipment_used,
                    trapping_duration=wc.trapping_duration,
                    monitoring_protocol=wc.monitoring_protocol,
                    capture_myopathy_treatment=wc.capture_myopathy_treatment,
                    opportunistic_species=wc.opportunistic_species,
                    release_procedure=wc.release_procedure,
                    transport_type=wc.transport_type,
                    transport_description=wc.transport_description,
                    animals_tagged=wc.animals_tagged,
                    health_observations=wc.health_observations,
                    physiological_parameters=wc.physiological_parameters,
                    measurement_frequency=wc.measurement_frequency,
                    normal_ranges=wc.normal_ranges,
                    out_of_range_protocol=wc.out_of_range_protocol
                )
            if hasattr(original, 'field_safety'):
                fs = original.field_safety
                FieldSafetyPrecautions.objects.create(
                    submission=new_submission,
                    decontamination_procedures=fs.decontamination_procedures,
                    ppe_description=fs.ppe_description
                )
            if hasattr(original, 'field_permits'):
                permit = original.field_permits
                FieldStudyPermit.objects.create(
                    submission=new_submission,
                    permits_required=permit.permits_required,
                    permit_details=permit.permit_details
                )
            for person in original.personnel_entries.all():
                IACUCPersonnel.objects.create(
                    submission=new_submission,
                    business_role=person.business_role,
                    name=person.name,
                    organization=person.organization,
                    department=person.department,
                    home_phone=person.home_phone,
                    email=person.email,
                    activities_description=person.activities_description,
                    training_completed=person.training_completed,
                    training_date=person.training_date,
                    degrees=person.degrees,
                    experience_and_qualifications=person.experience_and_qualifications,
                    years_of_experience=person.years_of_experience,
                    orientation_training_complete=person.orientation_training_complete,
                    submitted_achs_questionnaire=person.submitted_achs_questionnaire,
                    will_handle_animals=person.will_handle_animals,
                    activity_description=person.activity_description
                )
            if hasattr(original, 'database_search'):
                db = original.database_search
                DatabaseSearch.objects.create(
                    submission=new_submission,
                    animals_in_pain_d_or_e=db.animals_in_pain_d_or_e,
                    databases_used=db.databases_used,
                    search_terms=db.search_terms,
                    consultations=db.consultations,
                    journals=db.journals,
                    scientific_meetings=db.scientific_meetings,
                    alternatives_reason=db.alternatives_reason,
                    search_date=db.search_date,
                    years_covered=db.years_covered
                )
    return new_submission