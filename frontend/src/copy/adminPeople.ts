/**
 * Every sentence the admin's People & reporting and Lead Faculty mapping
 * screens write for themselves (SPEC §6.3).
 *
 * The shape is `leadershipModerationCopy.ts`'s: stable dotted keys, one entry
 * per string, one mapping, with `copy()` and `fillCopy()` as the only ways a
 * component reaches a word. The prefix is `admin_people.`, the one the
 * server's refusals for the same screens already use (`app/copy/admin_people.py`),
 * so a reader meets both sets of words on one screen. This file's keys all sit
 * under `admin_people.page.`, so none can collide with a refusal's key.
 *
 * ## What is deliberately not here
 *
 * **The server's refusals.** A revoke that leaves assignments reporting to the
 * one removed, a web login linked to somebody else, a file with a bad line and
 * an apply whose dry run is out of date are each answered with a sentence, and
 * the screen shows the one it was sent.
 *
 * ## The confidentiality line
 *
 * The surface owes none: everything here is a staff record and no student's
 * words, ratings or identity appear on it (E9 README decision 15).
 */

export const ADMIN_PEOPLE_COPY = {
  // The gate's two answers, in the register the leadership pages set (ADR 0196).
  'admin_people.page.session_ended_title': 'This page is not signed in',
  'admin_people.page.session_ended_body':
    'The session this page was opened with has ended. Open Pulse Surveys again to come back to it.',
  'admin_people.page.not_your_role_title': 'This page is not part of your role',
  'admin_people.page.not_your_role_body':
    'You are signed in, in a role this page is not for. Open Pulse Surveys again the way you usually do, and it opens the pages your role has.',
  'admin_people.page.unavailable':
    'This page could not be loaded just now. Reload the page to try again.',
  'admin_people.page.loading': 'Opening the table…',
  'admin_people.page.write_unavailable':
    'That change could not be sent just now. Reload the page to see whether it was recorded.',

  // The admin landing's two links; each is its page's own heading.
  'admin_people.page.people_heading': 'People & reporting',
  'admin_people.page.mappings_heading': 'Lead Faculty mapping',

  // People & reporting.
  'admin_people.page.people_intro':
    'Everyone in the reporting graph, the roles each person holds, and whom each role reports to. Build it from the top down: a role reports only to a role above it.',
  'admin_people.page.people_table_label': 'People and their roles',
  'admin_people.page.people_empty': 'There are no people yet.',
  'admin_people.page.column_name': 'Name',
  'admin_people.page.column_category': 'Category',
  'admin_people.page.column_roles': 'Roles and reporting lines',
  'admin_people.page.column_login': 'Web login',
  'admin_people.page.column_actions': 'Actions',
  'admin_people.page.sort_by': 'Sort by {column}',
  'admin_people.page.sorted_by': 'Sorted by {column}, {direction}',
  'admin_people.page.direction_ascending': 'ascending',
  'admin_people.page.direction_descending': 'descending',
  'admin_people.page.no_roles': 'No roles',
  'admin_people.page.reports_to': 'reports to {name} ({role})',
  'admin_people.page.reports_to_nobody': 'reports to nobody',
  'admin_people.page.login_linked': 'Linked',
  'admin_people.page.login_not_linked': 'Not linked',
  'admin_people.page.manage': 'Manage {name}',

  // Paging.
  'admin_people.page.pager_label': 'Pages',
  'admin_people.page.page_of': 'Page {page} of {pages}',
  'admin_people.page.previous_page': 'Previous page',
  'admin_people.page.next_page': 'Next page',
  'admin_people.page.total_people': '{total} people',
  'admin_people.page.total_mappings': '{total} mappings',

  // Adding a person.
  'admin_people.page.add_heading': 'Add a person',
  'admin_people.page.field_name': 'Name',
  'admin_people.page.field_category': 'Category',
  'admin_people.page.add_submit': 'Add person',
  'admin_people.page.person_added': 'Person added.',
  'admin_people.page.person_saved': 'Person saved.',

  // The selected person's panel.
  'admin_people.page.manage_heading': 'Manage {name}',
  'admin_people.page.close_panel': 'Close',
  'admin_people.page.save_person': 'Save name and category',
  'admin_people.page.grant_heading': 'Grant a role',
  'admin_people.page.field_role': 'Role',
  'admin_people.page.field_node': 'Granted at',
  'admin_people.page.node_option': '{name} ({parent})',
  'admin_people.page.node_choose': 'Choose where',
  'admin_people.page.nodes_unavailable': 'The places this role is granted at could not be loaded just now.',
  'admin_people.page.grant_submit': 'Grant role',
  'admin_people.page.role_granted': 'Role granted.',
  'admin_people.page.role_LEAD_FACULTY': 'Lead Faculty',
  'admin_people.page.role_CHAIR': 'Chair',
  'admin_people.page.role_ASSISTANT_DEAN': 'Assistant Dean',
  'admin_people.page.role_DEAN': 'Dean',
  'admin_people.page.role_VP_ACADEMICS': 'Vice President of Academics',
  'admin_people.page.role_CARE': 'Care',
  'admin_people.page.role_ADMIN': 'Admin',
  'admin_people.page.role_INSTRUCTOR': 'Instructor',
  'admin_people.page.assignments_heading': 'Roles held',
  'admin_people.page.revoke': 'Revoke {role}',
  'admin_people.page.revoke_at': 'Revoke {role} at {place}',
  'admin_people.page.assignment_at': '{role} at {place}',
  'admin_people.page.role_revoked': 'Role revoked.',
  'admin_people.page.reports_to_label': 'Reports to, for {assignment}',
  'admin_people.page.save_reports_to': 'Save reporting line for {assignment}',
  'admin_people.page.reports_to_none': 'Nobody',
  'admin_people.page.reports_to_option': '{name} ({role})',
  'admin_people.page.reports_to_saved': 'Reporting line saved.',
  'admin_people.page.options_unavailable':
    'The roles this one may report to could not be loaded just now.',
  'admin_people.page.login_heading': 'Web login',
  'admin_people.page.field_issuer': 'Identity provider issuer',
  'admin_people.page.field_subject': 'Identity provider subject',
  'admin_people.page.link_submit': 'Link web login',
  'admin_people.page.unlink_submit': 'Unlink web login',
  'admin_people.page.login_was_linked': 'Web login linked.',
  'admin_people.page.login_was_unlinked': 'Web login unlinked.',

  // Lead Faculty mapping.
  'admin_people.page.mappings_intro':
    'Which person leads each course. A course without a lead falls to its department chair.',
  'admin_people.page.mappings_table_label': 'Courses and their leads',
  'admin_people.page.mappings_empty': 'No course has a lead mapped yet.',
  'admin_people.page.column_course': 'Course',
  'admin_people.page.column_lead': 'Lead Faculty',

  // Export and import.
  'admin_people.page.export': 'Export CSV',
  'admin_people.page.exported': 'The file was downloaded.',
  'admin_people.page.import_heading': 'Import a CSV file',
  'admin_people.page.import_intro':
    'Choose a file to see what it would change. Nothing is applied until you have read the changes and chosen to apply them.',
  'admin_people.page.import_choose': 'CSV file',
  'admin_people.page.import_reading': 'Checking the file…',
  'admin_people.page.import_apply': 'Apply these changes',
  'admin_people.page.import_applying': 'Applying…',
  'admin_people.page.import_cancel': 'Cancel',
  'admin_people.page.import_retry': 'Check the file again',
  'admin_people.page.import_cancelled': 'The import was cancelled and nothing was changed.',
  'admin_people.page.import_applied': 'The import was applied. {summary}',
  'admin_people.page.import_unreadable': 'The file could not be read.',
  'admin_people.page.diff_heading': 'What this file would change',
  'admin_people.page.diff_summary_added': '{count} added',
  'admin_people.page.diff_summary_changed': '{count} changed',
  'admin_people.page.diff_summary_removed': '{count} removed',
  'admin_people.page.diff_summary_unmapped': '{count} left without a lead',
  'admin_people.page.diff_nothing': 'This file changes nothing.',
  'admin_people.page.diff_added_caption': 'Added',
  'admin_people.page.diff_changed_caption': 'Changed',
  'admin_people.page.diff_removed_caption': 'Removed',
  'admin_people.page.diff_unmapped_caption': 'Left without a lead',
  'admin_people.page.diff_column_before': 'Before',
  'admin_people.page.diff_column_after': 'After',
  'admin_people.page.diff_column_note': 'What happens',
} as const satisfies Record<string, string>;

/** Every key this surface publishes. */
export type AdminPeopleCopyKey = keyof typeof ADMIN_PEOPLE_COPY;

/**
 * The words behind one key.
 *
 * A function rather than direct indexing, so a key that is not one of this
 * surface's fails to compile rather than rendering `undefined`.
 */
export function copy(key: AdminPeopleCopyKey): string {
  return ADMIN_PEOPLE_COPY[key];
}

/** One entry with its `{placeholders}` filled in. */
export function fillCopy(key: AdminPeopleCopyKey, values: Readonly<Record<string, string>>): string {
  return copy(key).replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
