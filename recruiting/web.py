"""Server-rendered recruiting workflows; business rules live in services."""
from datetime import datetime, timezone

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import accounts, jobs, scheduling
from .auth import login_required
from .errors import DomainError

bp = Blueprint('web', __name__)


def form_skills():
    return request.form.get('skills', '').split(',')


def integer_field(name):
    try:
        value = int(request.form.get(name, ''))
        if not 0 < value < 2**63:
            raise ValueError
        return value
    except ValueError as error:
        raise DomainError(400, 'Choose a valid record.') from error


def utc_form_time(name):
    value = request.form.get(name, '')
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            raise ValueError
        return parsed.replace(tzinfo=timezone.utc).isoformat()
    except ValueError as error:
        raise DomainError(400, 'Enter a valid UTC date and time.') from error


@bp.get('/')
def index():
    return redirect(url_for('web.dashboard' if g.user else 'auth.login'))


@bp.get('/health')
def health():
    return {'status': 'ok'}


@bp.get('/dashboard')
@login_required
def dashboard():
    if g.user['role'] == 'Candidate':
        postings = jobs.recommendations(g.user)
        applications = jobs.applications(g.user)
        return render_template('dashboard.html', postings=postings, applications=applications,
                               profile=accounts.profile(g.user, g.user['id']))
    return render_template('dashboard.html', postings=jobs.owned_jobs(g.user),
                           company=accounts.company(g.user), slots=scheduling.employer_slots(g.user))


@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    candidate = g.user['role'] == 'Candidate'
    details = accounts.profile(g.user, g.user['id']) if candidate else accounts.company(g.user)
    error = None
    if request.method == 'POST':
        try:
            if candidate:
                accounts.update_profile(g.user, request.form.get('display_name', ''), form_skills(),
                                        request.form.get('resume', ''))
            else:
                accounts.update_company(g.user, request.form.get('name', ''), request.form.get('description', ''))
            flash('Your profile has been saved.', 'success')
            return redirect(url_for('web.profile'))
        except DomainError as exc:
            error = exc
    return render_template('profile.html', details=details, error=error), error.status if error else 200


@bp.route('/candidates/<int:candidate_id>/resume', methods=['GET', 'POST'])
@login_required
def resume(candidate_id):
    details = accounts.profile(g.user, candidate_id)
    if request.method == 'POST':
        accounts.update_profile(g.user, details['display_name'], details['skills'], request.form.get('resume', ''))
        flash('Your resume has been saved.', 'success')
        return redirect(url_for('web.resume', candidate_id=candidate_id))
    return render_template('resume.html', details=details)


@bp.route('/jobs/new', methods=['GET', 'POST'])
@login_required
def new_job():
    accounts.require_role(g.user, 'Employer')
    return edit_job_form(None)


@bp.route('/jobs/<int:job_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_job(job_id):
    accounts.require_role(g.user, 'Employer')
    return edit_job_form(jobs.job(g.user, job_id))


def edit_job_form(posting):
    error = None
    if request.method == 'POST':
        try:
            values = (request.form.get('title', ''), request.form.get('description', ''), form_skills())
            result = jobs.update_job(g.user, posting['id'], *values) if posting else jobs.create_job(g.user, *values)
            flash('Job updated.' if posting else 'Your job is now open for applications.', 'success')
            return redirect(url_for('web.job_detail', job_id=result['id']))
        except DomainError as exc:
            error = exc
    return render_template('job_form.html', posting=posting, error=error), error.status if error else 200


@bp.get('/jobs/<int:job_id>')
@login_required
def job_detail(job_id):
    posting = jobs.job(g.user, job_id)
    applied = None
    if g.user['role'] == 'Candidate':
        applied = next((a for a in jobs.applications(g.user) if a['job_id'] == job_id), None)
        from .matching import score
        posting['score'] = score(accounts.skills_for(g.user['id']), posting['skills'])
    return render_template('job_detail.html', posting=posting, applied=applied)


@bp.post('/jobs/<int:job_id>/delete')
@login_required
def delete_job(job_id):
    jobs.delete_job(g.user, job_id)
    flash('Job deleted.', 'success')
    return redirect(url_for('web.dashboard'))


@bp.post('/jobs/<int:job_id>/apply')
@login_required
def apply(job_id):
    result = jobs.apply(g.user, job_id)
    flash('Application submitted. You can follow its progress here.', 'success')
    return redirect(url_for('web.application_detail', application_id=result['id']))


@bp.get('/applications')
@login_required
def applications():
    return render_template('applications.html', applications=jobs.applications(g.user))


@bp.get('/applications/<int:application_id>')
@login_required
def application_detail(application_id):
    result = jobs.application(g.user, application_id)
    return render_template('application_detail.html', application=result,
                           slots=scheduling.available_slots(g.user, application_id))


@bp.get('/jobs/<int:job_id>/applicants')
@login_required
def applicants(job_id):
    rows = jobs.applicants(g.user, job_id)
    return render_template('applicants.html', posting=jobs.job(g.user, job_id), applicants=rows, statuses=jobs.STATUSES)


@bp.post('/applications/<int:application_id>/status')
@login_required
def set_status(application_id):
    result = jobs.set_status(g.user, application_id, request.form.get('status', ''))
    flash('Application status updated.', 'success')
    return redirect(url_for('web.applicants', job_id=result['job_id']))


@bp.route('/schedule', methods=['GET', 'POST'])
@login_required
def schedule():
    accounts.require_role(g.user, 'Employer')
    if request.method == 'POST':
        return create_slot(integer_field('job_id'))
    return render_template('schedule.html', postings=jobs.owned_jobs(g.user), slots=scheduling.employer_slots(g.user))


@bp.post('/jobs/<int:job_id>/slots')
@login_required
def create_slot(job_id):
    # Authorize before parsing so forbidden requests get 403, not a form error.
    accounts.require_role(g.user, 'Employer')
    jobs.job(g.user, job_id)
    scheduling.create_slot(g.user, job_id, utc_form_time('start'), utc_form_time('end'))
    flash('Interview slot added.', 'success')
    return redirect(url_for('web.schedule'))


@bp.post('/slots/<int:slot_id>/delete')
@login_required
def delete_slot(slot_id):
    scheduling.delete_slot(g.user, slot_id)
    flash('Interview slot deleted.', 'success')
    return redirect(url_for('web.schedule'))


@bp.post('/applications/<int:application_id>/book')
@login_required
def book(application_id):
    jobs.application(g.user, application_id)
    scheduling.book(g.user, application_id, integer_field('slot_id'))
    flash('Your interview is booked.', 'success')
    return redirect(url_for('web.application_detail', application_id=application_id))
