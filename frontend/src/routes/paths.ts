/**
 * Every parameterised or nested client address, relative to the router's
 * `/app` mount: one copy, read by `router.tsx` to declare each route and by the
 * pages to link to one another.
 *
 * A module of its own rather than a constant beside each page, because the
 * leadership and admin pages are loaded lazily (ci/bundle-budget.json): a route
 * table that imported a path from a page would pull that page into the first
 * chunk.
 */

export const LATEST_RESULTS_ROUTE = '/student/sections/$sectionId/results';
export const WEEK_RESULTS_ROUTE = '/student/sections/$sectionId/weeks/$courseWeek/results';

/** The instructor's report, and the route `WeekNav` navigates within. */
export const REPORT_ROUTE = '/instructor/sections/$sectionId';

/** The drill-down: one section, and the course week as a search parameter. */
export const DRILL_DOWN_ROUTE = '/leadership/sections/$sectionId';
export const COMPARISON_SETS_ROUTE = '/leadership/comparison-sets';
export const COMPARISON_SET_EDIT_ROUTE = '/leadership/comparison-sets/$setId';
export const REVIEW_QUEUE_ROUTE = '/leadership/review-queue';
export const EXCLUSION_LOG_ROUTE = '/leadership/exclusion-log';
export const RESPONSE_POLICY_ROUTE = '/leadership/response-policy';
export const RESPONSES_OWED_ROUTE = '/leadership/responses-owed';
export const ON_BEHALF_ROUTE = '/leadership/sections/$sectionId/weeks/$courseWeek/on-behalf';

export const PEOPLE_ROUTE = '/admin/people';
export const MAPPINGS_ROUTE = '/admin/lead-mappings';
