from isatools.model.v1 import *
import json
import logging
from networkx import DiGraph
from jsonschema import Draft4Validator, RefResolver
import os
from isatools.validate.utils import check_iso8601_date, check_encoding, check_data_files, check_pubmed_id, check_doi, \
    is_utf8, ValidationReport, ValidationError, isajson_load, isajson_link_objects

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


def load(fp):

    def _build_assay_graph(process_sequence=list()):
        G = DiGraph()
        for process in process_sequence:
            if process.next_process is not None or len(process.outputs) > 0:  # first check if there's some valid outputs to connect
                if len(process.outputs) > 0:
                    for output in [n for n in process.outputs if not isinstance(n, DataFile)]:
                        G.add_edge(process, output)
                else:  # otherwise just connect the process to the next one
                    G.add_edge(process, process.next_process)
            if process.prev_process is not None or len(process.inputs) > 0:
                if len(process.inputs) > 0:
                    for input_ in process.inputs:
                        G.add_edge(input_, process)
                else:
                    G.add_edge(process.prev_process, process)
        return G

    investigation = None
    logger.info('Opening file %s', fp)
    isajson = json.load(fp)
    if isajson is None:
        logger.error('There was a problem opening the JSON file')
    else:
        logger.debug('Start building the Investigation object')
        investigation = Investigation(
            identifier=isajson['identifier'],
            title=isajson['title'],
            description=isajson['description'],
            submission_date=isajson['submissionDate'],
            public_release_date=isajson['publicReleaseDate']
        )
        for comment_json in isajson['comments']:
            comment = Comment(
                name=comment_json['name'],
                value=comment_json['value'],
            )
            investigation.comments.append(comment)
        logger.debug('Populate the ontology source references')
        term_source_dict = {'': None}
        for ontologySourceReference_json in isajson['ontologySourceReferences']:
            logger.debug('Build Ontology Source Reference object')
            ontology_source_reference = OntologySourceReference(
                name=ontologySourceReference_json['name'],
                file=ontologySourceReference_json['file'],
                version=ontologySourceReference_json['version'],
                description=ontologySourceReference_json['description']
            )
            term_source_dict[ontology_source_reference.name] = ontology_source_reference
            investigation.ontology_source_references.append(ontology_source_reference)
        for publication_json in isajson['publications']:
            logger.debug('Build Investigation Publication object')
            publication = Publication(
                pubmed_id=publication_json['pubMedID'],
                doi=publication_json['doi'],
                author_list=publication_json['authorList'],
                title=publication_json['title'],
                status=OntologyAnnotation(
                    name=publication_json['status']['annotationValue'],
                    term_accession=publication_json['status']['termAccession'],
                    term_source=term_source_dict[publication_json['status']['termSource']]
                )
            )
            try:
                for comment_json in publication_json['comments']:
                    comment = Comment(
                        name=comment_json['name'],
                        value=comment_json['value']
                    )
                    publication.comments.append(comment)
            except KeyError:
                pass
            investigation.publications.append(publication)
        for person_json in isajson['people']:
            logger.debug('Build Investigation Person object')
            person = Person(
                last_name=person_json['lastName'],
                first_name=person_json['firstName'],
                mid_initials=person_json['midInitials'],
                email=person_json['email'],
                phone=person_json['phone'],
                fax=person_json['fax'],
                address=person_json['address'],
                affiliation=person_json['affiliation'],
            )
            for role_json in person_json['roles']:
                role = OntologyAnnotation(
                    name=role_json['annotationValue'],
                    term_accession=role_json['termAccession'],
                    term_source=term_source_dict[role_json['termSource']]
                )
                person.roles.append(role)
            for comment_json in person_json['comments']:
                comment = Comment(
                    name=comment_json['name'],
                    value=comment_json['value'],
                )
                person.comments.append(comment)
            investigation.contacts.append(person)
        logger.debug('Start building Studies objects')
        samples_dict = dict()
        sources_dict = dict()
        categories_dict = dict()
        protocols_dict = dict()
        factors_dict = dict()
        parameters_dict = dict()
        units_dict = dict()
        process_dict = dict()

        # populate assay characteristicCategories first
        for study_json in isajson['studies']:
            for assay_json in study_json['assays']:
                for assay_characteristics_category_json in assay_json['characteristicCategories']:
                    characteristic_category = OntologyAnnotation(
                        id_=assay_characteristics_category_json['@id'],
                        name=assay_characteristics_category_json['characteristicType']['annotationValue'],
                        term_source=term_source_dict[assay_characteristics_category_json['characteristicType']['termSource']],
                        term_accession=assay_characteristics_category_json['characteristicType']['termAccession'],
                    )
                    # study.characteristic_categories.append(characteristic_category)
                    categories_dict[characteristic_category.id] = characteristic_category
        for study_json in isajson['studies']:
            logger.debug('Start building Study object')
            study = Study(
                identifier=study_json['identifier'],
                title=study_json['title'],
                description=study_json['description'],
                submission_date=study_json['submissionDate'],
                public_release_date=study_json['publicReleaseDate'],
                filename=study_json['filename']
            )
            try:
                for comment_json in study_json['comments']:
                    comment = Comment(
                        name=comment_json['name'],
                        value=comment_json['value'],
                    )
                    study.comments.append(comment)
            except KeyError:
                pass
            for study_characteristics_category_json in study_json['characteristicCategories']:
                characteristic_category = OntologyAnnotation(
                    id_=study_characteristics_category_json['@id'],
                    name=study_characteristics_category_json['characteristicType']['annotationValue'],
                    term_source=term_source_dict[study_characteristics_category_json['characteristicType']['termSource']],
                    term_accession=study_characteristics_category_json['characteristicType']['termAccession'],
                )
                study.characteristic_categories.append(characteristic_category)
                categories_dict[characteristic_category.id] = characteristic_category
            for study_unit_json in study_json['unitCategories']:
                unit = OntologyAnnotation(id_=study_unit_json['@id'],
                                          name=study_unit_json['annotationValue'],
                                          term_source=term_source_dict[study_unit_json['termSource']],
                                          term_accession=study_unit_json['termAccession'])
                units_dict[unit.id] = unit
            for study_publication_json in study_json['publications']:
                logger.debug('Build Study Publication object')
                study_publication = Publication(
                    pubmed_id=study_publication_json['pubMedID'],
                    doi=study_publication_json['doi'],
                    author_list=study_publication_json['authorList'],
                    title=study_publication_json['title'],
                    status=OntologyAnnotation(
                        name=study_publication_json['status']['annotationValue'],
                        term_source=term_source_dict[study_publication_json['status']['termSource']],
                        term_accession=study_publication_json['status']['termAccession'],
                    )
                )
                try:
                    for comment_json in study_publication_json['comments']:
                        comment = Comment(
                            name=comment_json['name'],
                            value=comment_json['value']
                        )
                        study_publication.comments.append(comment)
                except KeyError:
                    pass
                study.publications.append(study_publication)
            for study_person_json in study_json['people']:
                logger.debug('Build Study Person object')
                study_person = Person(
                    last_name=study_person_json['lastName'],
                    first_name=study_person_json['firstName'],
                    mid_initials=study_person_json['midInitials'],
                    email=study_person_json['email'],
                    phone=study_person_json['phone'],
                    fax=study_person_json['fax'],
                    address=study_person_json['address'],
                    affiliation=study_person_json['affiliation'],
                )
                for role_json in study_person_json['roles']:
                    role = OntologyAnnotation(
                        name=role_json['annotationValue'],
                        term_accession=role_json['termAccession'],
                        term_source=term_source_dict[role_json['termSource']]
                    )
                    study_person.roles.append(role)
                try:
                    for comment_json in study_person_json['comments']:
                        comment = Comment(
                            name=comment_json['name'],
                            value=comment_json['value'],
                        )
                        study_person.comments.append(comment)
                except KeyError:
                    pass
                study.contacts.append(study_person)
            for design_descriptor_json in study_json['studyDesignDescriptors']:
                logger.debug('Build Ontology Annotation object (Study Design Descriptor)')
                design_descriptor = OntologyAnnotation(
                    name=design_descriptor_json['annotationValue'],
                    term_accession=design_descriptor_json['termAccession'],
                    term_source=term_source_dict[design_descriptor_json['termSource']]
                )
                study.design_descriptors.append(design_descriptor)
            for protocol_json in study_json['protocols']:
                logger.debug('Build Study Protocol object')
                protocol = Protocol(
                    id_=protocol_json['@id'],
                    name=protocol_json['name'],
                    uri=protocol_json['uri'],
                    description=protocol_json['description'],
                    version=protocol_json['version'],
                    protocol_type=OntologyAnnotation(
                        name=protocol_json['protocolType']['annotationValue'],
                        term_accession=protocol_json['protocolType']['termAccession'],
                        term_source=term_source_dict[protocol_json['protocolType']['termSource']]
                    )
                )
                for parameter_json in protocol_json['parameters']:
                    parameter = ProtocolParameter(
                        id_=parameter_json['@id'],
                        parameter_name=OntologyAnnotation(
                            name=parameter_json['parameterName']['annotationValue'],
                            term_source=term_source_dict[parameter_json['parameterName']['termSource']],
                            term_accession=parameter_json['parameterName']['termAccession']
                        )
                    )
                    protocol.parameters.append(parameter)
                    parameters_dict[parameter.id] = parameter
                for component_json in protocol_json['components']:
                    component = ProtocolComponent(
                        name=component_json['componentName'],
                        component_type=OntologyAnnotation(
                            name=component_json['componentType']['annotationValue'],
                            term_source=term_source_dict[component_json['componentType']['termSource']],
                            term_accession=component_json['componentType']['termAccession']
                        )
                    )
                    protocol.components.append(component)
                study.protocols.append(protocol)
                protocols_dict[protocol.id] = protocol
            for factor_json in study_json['factors']:
                logger.debug('Build Study Factor object')
                factor = StudyFactor(
                    id_=factor_json['@id'],
                    name=factor_json['factorName'],
                    factor_type=OntologyAnnotation(
                        name=factor_json['factorType']['annotationValue'],
                        term_accession=factor_json['factorType']['termAccession'],
                        term_source=term_source_dict[factor_json['factorType']['termSource']]
                    )
                )
                study.factors.append(factor)
                factors_dict[factor.id] = factor
            for source_json in study_json['materials']['sources']:
                logger.debug('Build Source object')
                source = Source(
                    id_=source_json['@id'],
                    name=source_json['name'][7:],
                )
                for characteristic_json in source_json['characteristics']:
                    logger.debug('Build Ontology Annotation object (Characteristic)')
                    value = characteristic_json['value']
                    unit = None
                    characteristic = Characteristic(category=categories_dict[characteristic_json['category']['@id']],)
                    if isinstance(value, dict):
                        try:
                            value = OntologyAnnotation(
                                name=characteristic_json['value']['annotationValue'],
                                term_source=term_source_dict[characteristic_json['value']['termSource']],
                                term_accession=characteristic_json['value']['termAccession'])
                        except KeyError:
                            raise IOError("Can't create value as annotation")
                    elif isinstance(value, int) or isinstance(value, float):
                        try:
                            unit = units_dict[characteristic_json['unit']['@id']]
                        except KeyError:
                            raise IOError("Can't create unit annotation")
                    elif not isinstance(value, str):
                        raise IOError("Unexpected type in characteristic value")
                    characteristic.value = value
                    characteristic.unit = unit
                    source.characteristics.append(characteristic)
                sources_dict[source.id] = source
                study.materials['sources'].append(source)
            for sample_json in study_json['materials']['samples']:
                logger.debug('Build Sample object')
                sample = Sample(
                    id_=sample_json['@id'],
                    name=sample_json['name'][7:],
                    derives_from=sample_json['derivesFrom']
                )
                for characteristic_json in sample_json['characteristics']:
                    logger.debug('Build Ontology Annotation object (Characteristic)')
                    value = characteristic_json['value']
                    unit = None
                    characteristic = Characteristic(
                            category=categories_dict[characteristic_json['category']['@id']])
                    if isinstance(value, dict):
                        try:
                            value = OntologyAnnotation(
                                name=characteristic_json['value']['annotationValue'],
                                term_source=term_source_dict[characteristic_json['value']['termSource']],
                                term_accession=characteristic_json['value']['termAccession'])
                        except KeyError:
                            raise IOError("Can't create value as annotation")
                    elif isinstance(value, int) or isinstance(value, float):
                        try:
                            unit = units_dict[characteristic_json['unit']['@id']]
                        except KeyError:
                            raise IOError("Can't create unit annotation")
                    elif not isinstance(value, str):
                        raise IOError("Unexpected type in characteristic value")
                    characteristic.value = value
                    characteristic.unit = unit
                    sample.characteristics.append(characteristic)
                for factor_value_json in sample_json['factorValues']:
                    logger.debug('Build Ontology Annotation object (Sample Factor Value)')
                    try:
                        factor_value = FactorValue(
                            factor_name=factors_dict[factor_value_json['category']['@id']],
                            value=OntologyAnnotation(
                                name=factor_value_json['value']['annotationValue'],
                                term_accession=factor_value_json['value']['termAccession'],
                                term_source=term_source_dict[factor_value_json['value']['termSource']],
                            ),

                        )
                    except TypeError:
                        factor_value = FactorValue(
                            factor_name=factors_dict[factor_value_json['category']['@id']],
                            value=factor_value_json['value'],
                            unit=units_dict[factor_value_json['unit']['@id']],
                        )
                    sample.factor_values.append(factor_value)
                samples_dict[sample.id] = sample
                study.materials['samples'].append(sample)
            for study_process_json in study_json['processSequence']:
                logger.debug('Build Process object')
                process = Process(
                    id_=study_process_json['@id'],
                    executes_protocol=protocols_dict[study_process_json['executesProtocol']['@id']],
                )
                try:
                    for comment_json in study_process_json['comments']:
                        comment = Comment(
                            name=comment_json['name'],
                            value=comment_json['value'],
                        )
                        process.comments.append(comment)
                except KeyError:
                    pass
                try:
                    process.date = study_process_json['date']
                except KeyError:
                    pass
                try:
                    process.performer = study_process_json['performer']
                except KeyError:
                    pass
                for parameter_value_json in study_process_json['parameterValues']:
                    if isinstance(parameter_value_json['value'], int) or isinstance(parameter_value_json['value'], float):
                        parameter_value = ParameterValue(
                            category=parameters_dict[parameter_value_json['category']['@id']],
                            value=parameter_value_json['value'],
                            unit=units_dict[parameter_value_json['unit']['@id']],
                        )
                        process.parameter_values.append(parameter_value)
                    else:
                        parameter_value = ParameterValue(
                            category=parameters_dict[parameter_value_json['category']['@id']],
                            )
                        try:
                            parameter_value.value = OntologyAnnotation(
                                name=parameter_value_json['value']['annotationValue'],
                                term_accession=parameter_value_json['value']['termAccession'],
                                term_source=term_source_dict[parameter_value_json['value']['termSource']],)
                        except TypeError:
                            parameter_value.value = parameter_value_json['value']
                        process.parameter_values.append(parameter_value)
                for input_json in study_process_json['inputs']:
                    input_ = None
                    try:
                        input_ = sources_dict[input_json['@id']]
                    except KeyError:
                        pass
                    finally:
                        try:
                            input_ = samples_dict[input_json['@id']]
                        except KeyError:
                            pass
                    if input_ is None:
                        raise IOError("Could not find input node in sources or samples dicts: " + input_json['@id'])
                    process.inputs.append(input_)
                for output_json in study_process_json['outputs']:
                    output = None
                    try:
                        output = sources_dict[output_json['@id']]
                    except KeyError:
                        pass
                    finally:
                        try:
                            output = samples_dict[output_json['@id']]
                        except KeyError:
                            pass
                    if output is None:
                        raise IOError("Could not find output node in sources or samples dicts: " + output_json['@id'])
                    process.outputs.append(output)
                study.process_sequence.append(process)
                process_dict[process.id] = process
            for study_process_json in study_json['processSequence']:  # 2nd pass
                try:
                    prev_proc = study_process_json['previousProcess']['@id']
                    process_dict[study_process_json['@id']].prev_process = process_dict[prev_proc]
                except KeyError:
                    pass
                try:
                    next_proc = study_process_json['nextProcess']['@id']
                    process_dict[study_process_json['@id']].next_process = process_dict[next_proc]
                except KeyError:
                    pass
            study.graph = _build_assay_graph(study.process_sequence)
            for assay_json in study_json['assays']:
                logger.debug('Start building Assay object')
                logger.debug('Build Study Assay object')
                assay = Assay(
                    measurement_type=OntologyAnnotation(
                        name=assay_json['measurementType']['annotationValue'],
                        term_accession=assay_json['measurementType']['termAccession'],
                        term_source=term_source_dict[assay_json['measurementType']['termSource']]
                    ),
                    technology_type=OntologyAnnotation(
                        name=assay_json['technologyType']['annotationValue'],
                        term_accession=assay_json['technologyType']['termAccession'],
                        term_source=term_source_dict[assay_json['technologyType']['termSource']]
                    ),
                    technology_platform=assay_json['technologyPlatform'],
                    filename=assay_json['filename']
                )
                for assay_unit_json in assay_json['unitCategories']:
                    unit = OntologyAnnotation(id_=assay_unit_json['@id'],
                                              name=assay_unit_json['annotationValue'],
                                              term_source=term_source_dict[assay_unit_json['termSource']],
                                              term_accession=assay_unit_json['termAccession'])
                    units_dict[unit.id] = unit
                data_dict = dict()
                for data_json in assay_json['dataFiles']:
                    logger.debug('Build Data object')
                    data_file = DataFile(
                        id_=data_json['@id'],
                        filename=data_json['name'],
                        label=data_json['type'],
                    )
                    try:
                        for comment_json in data_json['comments']:
                            comment = Comment(
                                name=comment_json['name'],
                                value=comment_json['value'],
                            )
                            data_file.comments.append(comment)
                    except KeyError:
                        pass
                    data_dict[data_file.id] = data_file
                    assay.data_files.append(data_file)
                for sample_json in assay_json['materials']['samples']:
                    sample = samples_dict[sample_json['@id']]
                    assay.materials['samples'].append(sample)
                for assay_characteristics_category_json in assay_json['characteristicCategories']:
                    characteristic_category =OntologyAnnotation(
                        id_=assay_characteristics_category_json['@id'],
                        name=assay_characteristics_category_json['characteristicType']['annotationValue'],
                        term_source=term_source_dict[assay_characteristics_category_json['characteristicType']['termSource']],
                        term_accession=assay_characteristics_category_json['characteristicType']['termAccession'],
                    )
                    study.characteristic_categories.append(characteristic_category)
                    categories_dict[characteristic_category.id] = characteristic_category
                other_materials_dict = dict()
                for other_material_json in assay_json['materials']['otherMaterials']:
                    logger.debug('Build Material object')  # need to detect material types
                    material_name = other_material_json['name']
                    if material_name.startswith('labeledextract-'):
                        material_name = material_name[15:]
                    else:
                        material_name = material_name[8:]
                    material = Material(
                        id_=other_material_json['@id'],
                        name=material_name,
                        type_=other_material_json['type'],
                    )
                    for characteristic_json in other_material_json['characteristics']:
                        characteristic = Characteristic(
                            category=categories_dict[characteristic_json['category']['@id']],
                            value=OntologyAnnotation(
                                name=characteristic_json['value']['annotationValue'],
                                term_source=term_source_dict[characteristic_json['value']['termSource']],
                                term_accession=characteristic_json['value']['termAccession'],
                            )
                        )
                        material.characteristics.append(characteristic)
                    assay.materials['other_material'].append(material)
                    other_materials_dict[material.id] = material
                for assay_process_json in assay_json['processSequence']:
                    process = Process(
                        id_=assay_process_json['@id'],
                        executes_protocol=protocols_dict[assay_process_json['executesProtocol']['@id']]
                    )
                    try:
                        for comment_json in assay_process_json['comments']:
                            comment = Comment(
                                name=comment_json['name'],
                                value=comment_json['value'],
                            )
                            process.comments.append(comment)
                    except KeyError:
                        pass
                    # additional properties, currently hard-coded special cases
                    if process.executes_protocol.protocol_type.name == 'data collection' and assay.technology_type.name == 'DNA microarray':
                        process.additional_properties['Scan Name'] = assay_process_json['name']
                    elif process.executes_protocol.protocol_type.name == 'nucleic acid sequencing':
                        process.additional_properties['Assay Name'] = assay_process_json['name']
                    elif process.executes_protocol.protocol_type.name == 'nucleic acid hybridization':
                        process.additional_properties['Hybridization Assay Name'] = assay_process_json['name']
                    elif process.executes_protocol.protocol_type.name == 'data transformation':
                        process.additional_properties['Data Transformation Name'] = assay_process_json['name']
                    elif process.executes_protocol.protocol_type.name == 'data normalization':
                        process.additional_properties['Normalization Name'] = assay_process_json['name']
                    for input_json in assay_process_json['inputs']:
                        input_ = None
                        try:
                            input_ = samples_dict[input_json['@id']]
                        except KeyError:
                            pass
                        finally:
                            try:
                                input_ = other_materials_dict[input_json['@id']]
                            except KeyError:
                                pass
                            finally:
                                try:
                                    input_ = data_dict[input_json['@id']]
                                except KeyError:
                                    pass
                        if input_ is None:
                            raise IOError("Could not find input node in samples or materials or data dicts: " +
                                          input_json['@id'])
                        process.inputs.append(input_)
                    for output_json in assay_process_json['outputs']:
                        output = None
                        try:
                            output = samples_dict[output_json['@id']]
                        except KeyError:
                            pass
                        finally:
                            try:
                                output = other_materials_dict[output_json['@id']]
                            except KeyError:
                                pass
                            finally:
                                    try:
                                        output = data_dict[output_json['@id']]
                                    except KeyError:
                                        pass
                        if output is None:
                            raise IOError("Could not find output node in samples or materials or data dicts: " +
                                          output_json['@id'])
                        process.outputs.append(output)
                    for parameter_value_json in assay_process_json['parameterValues']:
                        if parameter_value_json['category']['@id'] == '#parameter/Array_Design_REF':  # Special case
                            process.additional_properties['Array Design REF'] = parameter_value_json['value']
                        elif isinstance(parameter_value_json['value'], int) or \
                                isinstance(parameter_value_json['value'], float):
                            parameter_value = ParameterValue(
                                category=parameters_dict[parameter_value_json['category']['@id']],
                                value=parameter_value_json['value'],
                                unit=units_dict[parameter_value_json['unit']['@id']]
                            )
                            process.parameter_values.append(parameter_value)
                        else:
                            parameter_value = ParameterValue(
                                category=parameters_dict[parameter_value_json['category']['@id']],
                                )
                            try:
                                parameter_value.value = OntologyAnnotation(
                                    name=parameter_value_json['value']['annotationValue'],
                                    term_accession=parameter_value_json['value']['termAccession'],
                                    term_source=term_source_dict[parameter_value_json['value']['termSource']],)
                            except TypeError:
                                parameter_value.value = parameter_value_json['value']
                            process.parameter_values.append(parameter_value)
                    assay.process_sequence.append(process)
                    process_dict[process.id] = process
                    for assay_process_json in assay_json['processSequence']:  # 2nd pass
                        try:
                            prev_proc = assay_process_json['previousProcess']['@id']
                            process_dict[assay_process_json['@id']].prev_process = process_dict[prev_proc]
                        except KeyError:
                            pass
                        try:
                            next_proc = assay_process_json['nextProcess']['@id']
                            process_dict[assay_process_json['@id']].next_process = process_dict[next_proc]
                        except KeyError:
                            pass
                    assay.graph = _build_assay_graph(assay.process_sequence)
                study.assays.append(assay)
            logger.debug('End building Study object')
            investigation.studies.append(study)
        logger.debug('End building Studies objects')
        logger.debug('End building Investigation object')
    return investigation

def validate_isajson(isa_json, report):
    """Validate JSON"""

    def _check_isa_schemas(isa_json):
        investigation_schema_path = os.path.join(
            os.path.dirname(__file__) + '/schemas/isa_model_version_1_0_schemas/core/investigation_schema.json')
        investigation_schema = json.load(open(investigation_schema_path))
        resolver = RefResolver('file://' + investigation_schema_path, investigation_schema)
        validator = Draft4Validator(investigation_schema, resolver=resolver)
        validator.validate(isa_json)

    def _check_filenames(isa_json, report):
        for study in isa_json['studies']:
            if study['filename'] is '':
                report.warn("A study filename is missing")
            for assay in study['assays']:
                if assay['filename'] is '':
                    report.warn("An assay filename is missing")

    def _check_ontology_sources(isa_json, report):
        ontology_source_refs = ['']  # initalize with empty string as the default none ref
        for ontology_source in isa_json['ontologySourceReferences']:
            if ontology_source['name'] is '':
                report.warn("An Ontology Source Reference is missing Term Source Name, so can't be referenced")
            else:
                ontology_source_refs.append(ontology_source['name'])
        return ontology_source_refs

    def _check_date_formats(isa_json, report):
        check_iso8601_date(isa_json['publicReleaseDate'], report)
        check_iso8601_date(isa_json['submissionDate'], report)
        for study in isa_json['studies']:
            check_iso8601_date(study['publicReleaseDate'], report)
            check_iso8601_date(study['submissionDate'], report)
            for process in study['processSequence']:
                check_iso8601_date(process['date'], report)

    def _check_term_source_refs(isa_json, ontology_source_refs, report):
        # get all matching annotation patterns by traversing the whole json structure
        if isinstance(isa_json, dict):
            if set(isa_json.keys()) == {'annotationValue', 'termAccession', 'termSource'} or \
                            set(isa_json.keys()) == {'@id', 'annotationValue', 'termAccession', 'termSource'}:
                if isa_json['termSource'] not in ontology_source_refs:
                    report.warn("Annotation {0} references {1} term source that has not been declared"
                                .format(isa_json['annotationValue'], isa_json['termSource']))
            for i in isa_json.keys():
                _check_term_source_refs(isa_json[i], ontology_source_refs, report)
        elif isinstance(isa_json, list):
            for j in isa_json:
                _check_term_source_refs(j, ontology_source_refs, report)

    def _check_pubmed_ids(isa_json, report):
        for ipub in isa_json['publications']:
            check_pubmed_id(ipub['pubMedID'], report)
        for study in isa_json['studies']:
            for spub in study['publications']:
                check_pubmed_id(spub['pubMedID'], report)

    def _check_dois(isa_json, report):
        for ipub in isa_json['publications']:
            check_doi(ipub['doi'], report)
        for study in isa_json['studies']:
            for spub in study['publications']:
                check_doi(spub['doi'], report)

    def _check_protocol_names(isa_json, report):
        protocol_refs = ['']  # initalize with empty string as the default none ref
        for study in isa_json['studies']:
            for protocol in study['protocols']:
                if protocol['name'] is '':
                    report.warn("A Protocol is missing Protocol Name, so can't be referenced in ISA-tab")
                else:
                    protocol_refs.append(protocol['name'])
        return protocol_refs

    def _check_protocol_parameter_names(isa_json, report):
        protocol_parameter_refs = ['']  # initalize with empty string as the default none ref
        for study in isa_json['studies']:
            for protocol in study['protocols']:
                for parameter in protocol['parameters']:
                    if parameter['parameterName'] is '':
                        report.warn("A Protocol Parameter is missing Name, so can't be referenced in ISA-tab")
                    else:
                        protocol_parameter_refs.append(parameter['parameterName'])
        return protocol_parameter_refs

    def _check_study_factor_names(isa_json, report):
        study_factor_refs = ['']  # initalize with empty string as the default none ref
        for study in isa_json['studies']:
            for factor in study['factors']:
                    if factor['factorName'] is '':
                        report.warn("A Study Factor is missing Name, so can't be referenced in ISA-tab")
                    else:
                        study_factor_refs.append(study_factor_refs)
        return study_factor_refs

    def _collect_object_refs(isa_json, object_refs):
        # get all matching annotation patterns by traversing the whole json structure
        if isinstance(isa_json, dict):
            if '@id' in set(isa_json.keys()) and len(set(isa_json.keys())) > 1:
                if isa_json['@id'] not in object_refs:
                    object_refs.append(isa_json['@id'])
            for i in isa_json.keys():
                _collect_object_refs(isa_json[i], object_refs)
        elif isinstance(isa_json, list):
            for j in isa_json:
                _collect_object_refs(j, object_refs)
        return object_refs

    def _collect_id_refs(isa_json, id_refs):
        # get all matching annotation patterns by traversing the whole json structure
        if isinstance(isa_json, dict):
            if '@id' in set(isa_json.keys()) and len(set(isa_json.keys())) == 1:
                if isa_json['@id'] not in id_refs:
                    id_refs.append(isa_json['@id'])
            for i in isa_json.keys():
                _collect_id_refs(isa_json[i], id_refs)
        elif isinstance(isa_json, list):
            for j in isa_json:
                _collect_id_refs(j, id_refs)
        return id_refs

    def _collect_term_source_refs(isa_json, id_refs):
        # get all matching annotation patterns by traversing the whole json structure
        if isinstance(isa_json, dict):
            if 'termSource' in set(isa_json.keys()) and len(set(isa_json.keys())) == 3:
                if isa_json['termSource'] not in id_refs:
                    id_refs.append(isa_json['termSource'])
            for i in isa_json.keys():
                _collect_term_source_refs(isa_json[i], id_refs)
        elif isinstance(isa_json, list):
            for j in isa_json:
                _collect_term_source_refs(j, id_refs)
        return id_refs

    def _check_object_refs(isa_json, object_refs, report):
        # get all matching id patterns by traversing the whole json structure
        if isinstance(isa_json, dict):
            if '@id' in set(isa_json.keys()) and len(set(isa_json.keys())) == 1:
                if isa_json['@id'] not in object_refs and isa_json['@id'] != '#parameter/Array_Design_REF':
                    report.error("Object reference {} not declared anywhere".format(isa_json['@id']))
            for i in isa_json.keys():
                _check_object_refs(isa_json=isa_json[i], object_refs=object_refs, report=report)
        elif isinstance(isa_json, list):
            for j in isa_json:
                _check_object_refs(j, object_refs, report)
        return object_refs

    def _check_object_usage(section, objects_declared, id_refs, report):
        for obj_ref in objects_declared:
            if obj_ref not in id_refs:
                report.warn("Object reference {0} not used anywhere in {1}".format(obj_ref, section))

    try:  # if can load the JSON (if the JSON is well-formed already), validate the JSON against our schemas
        _check_isa_schemas(isa_json)
        # if the JSON is validated against ISA JSON, let's start checking content
        _check_filenames(isa_json=isa_json, report=report)  # check if tab filenames are present for converting back
        ontology_source_refs = _check_ontology_sources(isa_json=isa_json, report=report)  # check if ontology sources are declared with enough info
        _check_date_formats(isa_json=isa_json, report=report)  # check if dates are all ISO8601 compliant
        _check_term_source_refs(isa_json=isa_json, ontology_source_refs=ontology_source_refs, report=report)  # check if ontology refs refer to ontology source
        _check_pubmed_ids(isa_json=isa_json, report=report)
        _check_dois(isa_json=isa_json, report=report)
        _check_protocol_names(isa_json=isa_json, report=report)
        _check_protocol_parameter_names(isa_json=isa_json, report=report)
        _check_study_factor_names(isa_json=isa_json, report=report)
        _check_object_refs(isa_json=isa_json, object_refs=_collect_object_refs(isa_json=isa_json, object_refs=list()), report=report)

        # check protocols declared are used
        for i, study in enumerate(isa_json['studies']):
            prot_obj_ids = list()
            for protocol in study['protocols']:
                prot_obj_ids.append(protocol['@id'])
            study_id = "study loc {} (study location autocalculated by validator - Study ID in JSON not present)".format(i+1)
            if study['identifier'] != '':
                study_id = study['identifier']
            _check_object_usage(section=study_id, objects_declared=prot_obj_ids, id_refs=_collect_id_refs(isa_json=isa_json, id_refs=list()), report=report)

        # check study factors declared are used
        for i, study in enumerate(isa_json['studies']):
            factor_obj_ids = list()
            for factor in study['factors']:
                factor_obj_ids.append(factor['@id'])
            study_id = "study loc {} (study location autocalculated by validator - Study ID in JSON not present)".format(i+1)
            if study['identifier'] != '':
                study_id = study['identifier']
            _check_object_usage(section=study_id, objects_declared=factor_obj_ids, id_refs=_collect_id_refs(isa_json=isa_json, id_refs=list()), report=report)
        ontology_source_refs = [ref['name'] for ref in isa_json['ontologySourceReferences']]
        _check_object_usage(section='investigation (term source check)', objects_declared=ontology_source_refs, id_refs=_collect_term_source_refs(isa_json=isa_json, id_refs=list()), report=report)

        dir_context = os.path.dirname(report.file_name)
        for study in isa_json['studies']:
            for assay in study['assays']:
                check_data_files(data_files=assay['dataFiles'], dir_context=dir_context, report=report)
        i = isajson_load(open(report.file_name))  # load with alternative implementation to enable link checking
        isajson_link_objects(investigation=i, report=report)
        # i = load(open(report.file_name))  # load with fully featured working isajson.load()
        # check_against_config(i.studies)
    except ValidationError as isa_schema_validation_error:
        raise isa_schema_validation_error


def validate(fp):  # default reporting
    """Validate JSON file"""
    report = ValidationReport(fp.name)
    check_encoding(fp, report=report)
    if not is_utf8(fp):
        report.fatal("File is not UTF-8 encoded, not proceeding with json.load as it will fail")
    else:
        try:  # first, try open the file as a JSON
            try:
                isa_json = json.load(fp=fp)
                validate_isajson(isa_json, report)
            except ValueError as json_load_error:
                report.fatal("There was an error when trying to parse the JSON")
                raise json_load_error
        except SystemError as system_error:
            report.fatal("There was a general system error")
            raise system_error
    return report


def get_source_ids(study_json):
    """Used for rule 1002"""
    return [source['@id'] for source in study_json['materials']['sources']]


def get_sample_ids(study_json):
    """Used for rule 1003"""
    return [sample['@id'] for sample in study_json['materials']['samples']]


def get_material_ids(study_json):
    """Used for rule 1005"""
    material_ids = list()
    for assay_json in study_json['assays']:
        material_ids.extend([material['@id'] for material in assay_json['materials']['otherMaterials']])
    return material_ids


def get_data_file_ids(study_json):
    """Used for rule 1004"""
    data_file_ids = list()
    for assay_json in study_json['assays']:
        data_file_ids.extend([data_file['@id'] for data_file in assay_json['dataFiles']])
    return data_file_ids


def get_io_ids_in_process_sequence(study_json):
    """Used for rules 1001-1005"""
    all_process_sequences = study_json['processSequence']
    for assay_json in study_json['assays']:
        all_process_sequences.extend(assay_json['processSequence'])
    return [elem for iterabl in [[i['@id'] for i in process['inputs']] + [o['@id'] for o in process['outputs']] for process in
                                 all_process_sequences] for elem in iterabl]


def check_material_ids_declared_used(study_json, id_collector_func):
    """Used for rules 1001-1005

    e.g. check_ids_used(study, get_source_ids)  # study is some json, get_source_ids is the collector function
    """
    node_ids = id_collector_func(study_json)
    io_ids_in_process_sequence = get_io_ids_in_process_sequence(study_json)
    is_node_ids_used = set(node_ids).issubset(set(io_ids_in_process_sequence))
    if not is_node_ids_used:
        print("Not all node IDs in {} used by inputs/outputs {}".format(node_ids, io_ids_in_process_sequence))


def check_material_ids_not_declared_used(study_json):
    node_ids = get_source_ids(study_json) + get_sample_ids(study_json) + get_material_ids(study_json) + \
               get_data_file_ids(study_json)
    io_ids_in_process_sequence = get_io_ids_in_process_sequence(study_json)
    if len(set(io_ids_in_process_sequence)) - len(set(node_ids)) > 0:
        diff = set(io_ids_in_process_sequence) - set(node_ids)
        print("There are some inputs/outputs IDs {} not found in sources, samples, materials or data files declared"
              .format(list(diff)))


def check_process_sequence_links(process_sequence_json):
    """Used for rule 1006"""
    process_ids = [process['@id'] for process in process_sequence_json]
    for process in process_sequence_json:
        try:
            if process['previousProcess']['@id'] not in process_ids:
                print("previousProcess link {} in process {} does not refer to another process in sequence"
                      .format(process['previousProcess']['@id'], process['@id']))
        except KeyError:
            pass
        try:
            if process['nextProcess']['@id'] not in process_ids:
                print("nextProcess link {} in process {} does not refer to another process in sequence"
                      .format(process['nextProcess']['@id'], process['@id']))
        except KeyError:
            pass


def get_study_protocol_ids(study_json):
    """Used for rule 1007"""
    return [protocol['@id'] for protocol in study_json['protocols']]


def check_process_protocol_ids_usage(study_json):
    """Used for rules 1007 and 1019"""
    protocol_ids_declared = get_study_protocol_ids(study_json)
    process_sequence = study_json['processSequence']
    protocol_ids_used = list()
    for process in process_sequence:
        try:
            protocol_ids_used.append(process['executesProtocol']['@id'])
        except KeyError:
            pass
    for assay in study_json['assays']:
        process_sequence = assay['processSequence']
        for process in process_sequence:
            try:
                protocol_ids_used.append(process['executesProtocol']['@id'])
            except KeyError:
                pass
    if len(set(protocol_ids_used) - set(protocol_ids_declared)) > 0:
        diff = set(protocol_ids_used) - set(protocol_ids_declared)
        print("There are protocol IDs {} used in a study or assay process sequence not declared"
              .format(list(diff)))
    elif len(set(protocol_ids_declared) - set(protocol_ids_used)) > 0:
        diff = set(protocol_ids_declared) - set(protocol_ids_used)
        print("There are some protocol IDs declared {} not used in any study or assay process sequence"
              .format(list(diff)))


def get_study_protocols_parameter_ids(study_json):
    """Used for rule 1009"""
    return [elem for iterabl in [[param['@id'] for param in protocol['parameters']] for protocol in
                                 study_json['protocols']] for elem in iterabl]


def get_parameter_value_parameter_ids(study_json):
    """Used for rule 1009"""
    study_pv_parameter_ids = [elem for iterabl in
                              [[parameter_value['category']['@id'] for parameter_value in process['parameterValues']]
                               for process in study_json['processSequence']] for elem in iterabl]
    for assay in study_json['assays']:
        study_pv_parameter_ids.extend([elem for iterabl in
                                       [[parameter_value['category']['@id'] for parameter_value in
                                         process['parameterValues']]
                                        for process in assay['processSequence']] for elem in iterabl]
                                      )
    return study_pv_parameter_ids


def check_protocol_parameter_ids_usage(study_json):
    protocols_declared = get_study_protocols_parameter_ids(study_json)
    protocols_used = get_parameter_value_parameter_ids(study_json)
    if len(set(protocols_used) - set(protocols_declared)) > 0:
        diff = set(protocols_used) - set(protocols_declared)
        print("There are protocol parameters {} used in a study or assay process not declared in any protocol"
              .format(list(diff)))
    elif len(set(protocols_declared) - set(protocols_used)) > 0:
        diff = set(protocols_declared) - set(protocols_used)
        print("There are some protocol parameters declared {} not used in any study or assay process"
              .format(list(diff)))


def get_characteristic_category_ids(study_or_assay_json):
    """Used for rule 1013"""
    return [category['@id'] for category in study_or_assay_json['characteristicCategories']]


def get_characteristic_category_ids_in_study_materials(study_json):
    """Used for rule 1013"""
    return [elem for iterabl in
            [[characteristic['category']['@id'] for characteristic in material['characteristics']] for material in
             study_json['materials']['sources'] + study_json['materials']['samples']] for elem in iterabl]


def get_characteristic_category_ids_in_assay_materials(assay_json):
    """Used for rule 1013"""
    return [elem for iterabl in [[characteristic['category']['@id']  for characteristic in material['characteristics']]
                                 if 'characteristics' in material.keys() else [] for material in
              assay_json['materials']['samples'] + assay_json['materials']['otherMaterials']] for elem in iterabl]


def check_characteristic_category_ids_usage(study_json):
    """Used for rule 1013"""
    characteristic_categories_declared = get_characteristic_category_ids(study_json)
    characteristic_categories_used = get_characteristic_category_ids_in_study_materials(study_json)
    if len(set(characteristic_categories_used) - set(characteristic_categories_declared)) > 0:
        diff = set(characteristic_categories_used) - set(characteristic_categories_declared)
        print("There are study characteristic categories {} used in a source or sample characteristic that have not been not declared"
              .format(list(diff)))
    elif len(set(characteristic_categories_declared) - set(characteristic_categories_used)) > 0:
        diff = set(characteristic_categories_declared) - set(characteristic_categories_used)
        print("There are some study characteristic categories declared {} that have not been used in any source or sample characteristic"
              .format(list(diff)))
    for assay in study_json['assays']:
        characteristic_categories_declared = get_characteristic_category_ids(assay)
        characteristic_categories_used = get_characteristic_category_ids_in_assay_materials(assay)
        if len(set(characteristic_categories_used) - set(characteristic_categories_declared)) > 0:
            diff = set(characteristic_categories_used) - set(characteristic_categories_declared)
            print(
                "There are assay characteristic categories {} used in a material characteristic that have not been not declared"
                .format(list(diff)))
        elif len(set(characteristic_categories_declared) - set(characteristic_categories_used)) > 0:
            diff = set(characteristic_categories_declared) - set(characteristic_categories_used)
            print(
                "There are some assay characteristic categories declared {} that have not been used in any material characteristic"
                .format(list(diff)))


def get_study_factor_ids(study_json):
    """Used for rule 1008 and 1020"""
    return [factor['@id'] for factor in study_json['factors']]


def get_study_factor_ids_in_sample_factor_values(study_json):
    """Used for rule 1008 and 1020"""
    return [elem for iterabl in [[factor['category']['@id'] for factor in sample['factorValues']] for sample in
                                 study_json['materials']['samples']] for elem in iterabl]


def check_study_factor_usage(study_json):
    """Used for rules 1008 and 1020"""
    factors_declared = get_study_factor_ids(study_json)
    factors_used = get_study_factor_ids_in_sample_factor_values(study_json)
    if len(set(factors_used) - set(factors_declared)) > 0:
        diff = set(factors_used) - set(factors_declared)
        print("There are study factors {} used in a sample factor value that have not been not declared"
              .format(list(diff)))
    elif len(set(factors_declared) - set(factors_used)) > 0:
        diff = set(factors_declared) - set(factors_used)
        print("There are some study factors declared {} that have not been used in any sample factor value"
              .format(list(diff)))


def get_unit_category_ids(study_or_assay_json):
    """Used for rule 1014"""
    return [category['@id'] for category in study_or_assay_json['unitCategories']]


def get_study_unit_category_ids_in_materials_and_processes(study_json):
    """Used for rule 1014"""
    study_characteristics_units_used = [elem for iterabl in
                                        [[characteristic['unit']['@id'] if 'unit' in characteristic.keys() else None for
                                          characteristic in material['characteristics']] for material in
                                         study_json['materials']['sources'] + study_json['materials']['samples']] for
                                        elem in iterabl]
    study_factor_value_units_used = [elem for iterabl in
                                     [[factor_value['unit']['@id'] if 'unit' in factor_value.keys() else None for
                                       factor_value in material['factorValues']] for material in
                                      study_json['materials']['samples']] for
                                     elem in iterabl]
    parameter_value_units_used = [elem for iterabl in[[parameter_value['unit']['@id'] if 'unit' in parameter_value.keys() else None for
                                   parameter_value in process['parameterValues']] for process in
                                  study_json['processSequence']] for
                                  elem in iterabl]
    return [x for x in study_characteristics_units_used + study_factor_value_units_used + parameter_value_units_used if x is not None]


def get_assay_unit_category_ids_in_materials_and_processes(assay_json):
    """Used for rule 1014"""
    assay_characteristics_units_used = [elem for iterabl in [[characteristic['unit']['@id'] if 'unit' in
                                        characteristic.keys() else None for characteristic in material['characteristics']] if 'characteristics' in material.keys() else None for
                                     material in assay_json['materials']['otherMaterials']] for elem in iterabl]
    parameter_value_units_used = [elem for iterabl in[[parameter_value['unit']['@id'] if 'unit' in parameter_value.keys() else None for
                                   parameter_value in process['parameterValues']] for process in
                                                      assay_json['processSequence']] for
                                  elem in iterabl]
    return [x for x in assay_characteristics_units_used + parameter_value_units_used if x is not None]


def check_unit_category_ids_usage(study_json):
    """"""
    units_declared = get_unit_category_ids(study_json)
    for assay in study_json['assays']:
        units_declared.extend(get_unit_category_ids(assay))
    units_used = get_study_unit_category_ids_in_materials_and_processes(study_json)
    for assay in study_json['assays']:
        units_used.extend(get_assay_unit_category_ids_in_materials_and_processes(assay))
    if len(set(units_used) - set(units_declared)) > 0:
        diff = set(units_used) - set(units_declared)
        print("There are units {} used in a material or parameter value that have not been not declared"
              .format(list(diff)))
    elif len(set(units_declared) - set(units_used)) > 0:
        diff = set(units_declared) - set(units_used)
        print("There are some units declared {} that have not been used in any material or parameter value"
              .format(list(diff)))


def check_utf8(fp):
    """Used for rule 0010"""
    import chardet
    charset = chardet.detect(open(fp.name, 'rb').read())
    if charset['encoding'] is not 'UTF-8' and charset['encoding'] is not 'ascii':
        print("File should be UTF-8 encoding but found it is '{0}' encoding with {1} confidence"
                    .format(charset['encoding'], charset['confidence']))
        raise SystemError


def check_isa_schemas(isa_json):
    """Used for rule 0003"""
    investigation_schema_path = os.path.join(
        os.path.dirname(__file__) + '/schemas/isa_model_version_1_0_schemas/core/investigation_schema.json')
    investigation_schema = json.load(open(investigation_schema_path))
    resolver = RefResolver('file://' + investigation_schema_path, investigation_schema)
    validator = Draft4Validator(investigation_schema, resolver=resolver)
    validator.validate(isa_json)


def check_date_formats(isa_json):
    """Used for rule 3001"""
    def check_iso8601_date(date_str):
        if date_str is not '':
            try:
                iso8601.parse_date(date_str)
            except iso8601.ParseError:
                print("Date {} does not conform to ISO8601 format".format(date_str))
    import iso8601
    check_iso8601_date(isa_json['publicReleaseDate'])
    check_iso8601_date(isa_json['submissionDate'])
    for study in isa_json['studies']:
        check_iso8601_date(study['publicReleaseDate'])
        check_iso8601_date(study['submissionDate'])
        for process in study['processSequence']:
            check_iso8601_date(process['date'])


def check_dois(isa_json):
    """Used for rule 3002"""
    def check_doi(doi_str):
        if doi_str is not '':
            regexDOI = re.compile('(10[.][0-9]{4,}(?:[.][0-9]+)*/(?:(?![%"#? ])\\S)+)')
            if not regexDOI.match(doi_str):
                print("DOI {} does not conform to DOI format".format(doi_str))
    import re
    for ipub in isa_json['publications']:
        check_doi(ipub['doi'])
    for study in isa_json['studies']:
        for spub in study['publications']:
            check_doi(spub['doi'])


def check_filenames_present(isa_json):
    """Used for rule 3005"""
    for study in isa_json['studies']:
        if study['filename'] is '':
            print("A study filename is missing")
        for assay in study['assays']:
            if assay['filename'] is '':
                print("An assay filename is missing")


def check_pubmed_ids_format(isa_json):
    """Used for rule 3003"""
    def check_pubmed_id(pubmed_id_str):
        if pubmed_id_str is not '':
            pmid_regex = re.compile('[0-9]{8}')
            pmcid_regex = re.compile('PMC[0-9]{8}')
            if (pmid_regex.match(pubmed_id_str) is None) and (pmcid_regex.match(pubmed_id_str) is None):
                print("PubMed ID {} is not valid format".format(pubmed_id_str))
    import re
    for ipub in isa_json['publications']:
        check_pubmed_id(ipub['pubMedID'])
    for study in isa_json['studies']:
        for spub in study['publications']:
            check_pubmed_id(spub['pubMedID'])


def check_protocol_names(isa_json):
    """Used for rule 1010"""
    for study in isa_json['studies']:
        for protocol in study['protocols']:
            if protocol['name'] is '':
                print("A Protocol {} is missing Protocol Name, so can't be referenced in ISA-tab".format(protocol['@id']))


def check_protocol_parameter_names(isa_json):
    """Used for rule 1011"""
    for study in isa_json['studies']:
        for protocol in study['protocols']:
            for parameter in protocol['parameters']:
                if parameter['parameterName'] is '':
                    print("A Protocol Parameter {} is missing name, so can't be referenced in ISA-tab".format(parameter['@id']))


def check_study_factor_names(isa_json):
    """Used for rule 1012"""
    for study in isa_json['studies']:
        for factor in study['factors']:
            if factor['factorName'] is '':
                print("A Study Factor is missing name, so can't be referenced in ISA-tab".format(factor['@id']))


def check_ontology_sources(isa_json):
    """Used for rule 3008"""
    for ontology_source in isa_json['ontologySourceReferences']:
        if ontology_source['name'] is '':
            print("An Ontology Source Reference is missing Term Source Name, so can't be referenced in ISA-tab")


def get_ontology_source_refs(isa_json):
    """Used for rules 3007 and 3009"""
    return [ontology_source_ref['name'] for ontology_source_ref in isa_json['ontologySourceReferences']]


def walk_and_get_annotations(isa_json, collector):
    """Used for rules 3007 and 3009

    Usage:
      collector = list()
      walk_and_get_annotations(isa_json, collector)
      # and then like magic all your annotations from the JSON should be in the collector list
    """
    #  Walk JSON tree looking for ontology annotation structures in the JSON
    if isinstance(isa_json, dict):
        if set(isa_json.keys()) == {'annotationValue', 'termAccession', 'termSource'} or \
                        set(isa_json.keys()) == {'@id', 'annotationValue', 'termAccession', 'termSource'}:
            collector.append(isa_json)
        for i in isa_json.keys():
            walk_and_get_annotations(isa_json[i], collector)
    elif isinstance(isa_json, list):
        for j in isa_json:
            walk_and_get_annotations(j, collector)


def check_term_source_refs(isa_json):
    """Used for rules 3007 and 3009"""
    term_sources_declared = get_ontology_source_refs(isa_json)
    collector = list()
    walk_and_get_annotations(isa_json, collector)
    term_sources_used = [annotation['termSource'] for annotation in collector if annotation['termSource'] is not '']
    if len(set(term_sources_used) - set(term_sources_declared)) > 0:
        diff = set(term_sources_used) - set(term_sources_declared)
        print("There are ontology sources {} referenced in an annotation that have not been not declared"
              .format(list(diff)))
    elif len(set(term_sources_declared) - set(term_sources_used)) > 0:
        diff = set(term_sources_declared) - set(term_sources_used)
        print("There are some ontology sources declared {} that have not been used in any annotation"
              .format(list(diff)))


def check_term_accession_used_no_source_ref(isa_json):
    """Used for rule 3010"""
    collector = list()
    walk_and_get_annotations(isa_json, collector)
    terms_using_accession_no_source_ref = [annotation for annotation in collector if annotation['termAccession'] is not '' and annotation['termSource'] is '']
    if len(terms_using_accession_no_source_ref) > 0:
        print("There are ontology annotations with termAccession set but no termSource referenced: {}".format(terms_using_accession_no_source_ref))


def validate2(fp):
    try:
        check_utf8(fp=fp)  # Rule 0010
        try:
            isa_json = json.load(fp=fp)  # Rule 0002
            check_isa_schemas(isa_json=isa_json)  # Rule 0003
            for study_json in isa_json['studies']:
                check_material_ids_not_declared_used(study_json)  # Rules 1002-1005
            for study_json in isa_json['studies']:
                check_material_ids_declared_used(study_json, get_source_ids)  # Rule 1015
                check_material_ids_declared_used(study_json, get_sample_ids)  # Rule 1016
                check_material_ids_declared_used(study_json, get_material_ids)  # Rule 1017
                check_material_ids_declared_used(study_json, get_data_file_ids)  # Rule 1018
            for study_json in isa_json['studies']:
                check_characteristic_category_ids_usage(study_json)  # Rules 1013 and 1021
            for study_json in isa_json['studies']:
                check_unit_category_ids_usage(study_json)  # Rules 1014 and 1022
            for study_json in isa_json['studies']:
                check_process_sequence_links(study_json['processSequence'])  # Rule 1006
                for assay_json in study_json['assays']:
                    check_process_sequence_links(assay_json['processSequence'])  # Rule 1006
            for study_json in isa_json['studies']:
                check_process_protocol_ids_usage(study_json)  # Rules 1007 and 1019
            check_date_formats(isa_json)  # Rule 3001
            check_dois(isa_json)  # Rule 3002
            check_pubmed_ids_format(isa_json)  # Rule 3003
            check_filenames_present(isa_json)  # Rule 3005
            check_protocol_names(isa_json)  # Rule 1010
            check_protocol_parameter_names(isa_json)  # Rule 1011
            check_study_factor_names(isa_json)  # Rule 1012
            check_ontology_sources(isa_json)  # Rule 3008
            check_term_source_refs(isa_json)  # Rules 3007 and 3009
            check_term_accession_used_no_source_ref(isa_json)  # Rule 3010
            # if all ERRORS are resolved, then try and validate against configuration
        except ValueError as json_load_error:
            print("There was an error when trying to parse the JSON")
            raise json_load_error
    except SystemError as system_error:
        print("There was a general system error")
        raise system_error