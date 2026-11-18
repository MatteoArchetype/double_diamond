"""Read-only, original-record copy for an explicit unsaved Define revision draft."""
import copy
from .visit_review import read_visit


def read_frame_draft(database,visit_id,*,expected_revision):
    if type(expected_revision) is not int or expected_revision<0:raise ValueError('A current case revision is required.')
    review=read_visit(database,visit_id,expected_revision=expected_revision)
    if review['workflow_status']!='active' or review['active_phase']!='define' or review['active_visit_recorded']:
        raise ValueError('Return to an open Define visit through its human review before copying an earlier frame.')
    if review['visit']['phase']!='define' or review['visit']['record'] is None or review['is_latest_visit']:
        raise ValueError('Choose an earlier saved Define visit.')
    if review['context_status']!='verified_original':raise ValueError('The original frame context is unavailable; inspect the record and write a fresh draft instead.')
    return dict(type='unsaved_frame_draft',source_visit_id=visit_id,target_visit_id=review['active_visit_id'],
        based_on_state_revision=review['state_revision'],source_recorded_revision=review['recorded_revision'],
        record=copy.deepcopy(review['visit']['record']),approval_granted=False,persisted=False)
