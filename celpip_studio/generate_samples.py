"""
Generate 3 sample CELPIP Part 1 videos — Career & Work, Band 9-10.
One question per frequency tier: HIGH PRIORITY / PRACTICE / BONUS CHALLENGE.
Run from the celpip_studio directory:  python generate_samples.py
"""

import os, sys, time, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.video_builder import build_video

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'output', 'speaking', 'Part 1', 'Career Work', 'Band 9-10'
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Sample definitions ────────────────────────────────────────────────────────

SAMPLES = [

    # ── ★★★ HIGH PRIORITY ────────────────────────────────────────────────────
    {
        'freq':     'high',
        'filename': '01_Career_Quitting_Without_New_Job_Band9-10.mp4',
        'job_data': {
            'task_num':     1,
            'band':         '9_10',
            'category':     'Career & Work',
            'category_slug':'career_work',
            'freq':         'high',
            'title':        'Quitting Without a New Job',
            'question': (
                "Your friend says: \"I hate my job and I can't take it anymore. "
                "The work is stressful, my boss is demanding, and I feel burned out "
                "every day. I'm thinking about quitting right away, even though I don't "
                "have another job yet. What do you think I should do?\""
            ),
            'answer': (
                "I completely understand how difficult it must feel to be in such a "
                "draining situation — burnout is a serious issue that affects your "
                "health, your relationships, and your long-term performance. "
                "That said, I would strongly advise against quitting without a new "
                "job lined up, at least not immediately. "
                "First, financial security is absolutely essential. "
                "Without income, the stress of unemployment could quickly replace the "
                "stress of your current job and make your situation significantly worse. "
                "I would encourage you to start your job search actively right now, "
                "while you are still employed — update your resume, reach out to your "
                "professional network, and apply to positions that genuinely excite you. "
                "Second, try to create some distance from the most stressful parts of "
                "your current role in the meantime. "
                "If possible, speak privately with your manager or HR about your workload — "
                "sometimes a small adjustment in responsibilities can make things more "
                "manageable while you search. "
                "Finally, if your mental or physical health is genuinely at serious risk "
                "and you truly cannot continue, then leaving may be necessary — but only "
                "after you have saved at least three to six months of living expenses "
                "as a financial buffer. "
                "The goal is to leave on your own terms, with a clear plan, so that you "
                "are moving toward something better rather than simply running away "
                "from something difficult."
            ),
            'vocab': [
                {
                    'word':       'burnout',
                    'definition': 'complete physical and emotional exhaustion caused by prolonged stress',
                    'example':    'Her burnout made it impossible to focus on even simple tasks at work.',
                },
                {
                    'word':       'draining',
                    'definition': 'gradually exhausting one\'s energy or emotional resources',
                    'example':    'Working with difficult clients all day can be incredibly draining.',
                },
                {
                    'word':       'financial buffer',
                    'definition': 'savings set aside to cover expenses during uncertain or difficult periods',
                    'example':    'A financial buffer of three months gave him confidence to resign.',
                },
                {
                    'word':       'manageable',
                    'definition': 'able to be handled, controlled, or dealt with effectively',
                    'example':    'Breaking the project into smaller tasks made it feel more manageable.',
                },
                {
                    'word':       'professional network',
                    'definition': 'a group of contacts in one\'s industry who can provide opportunities and referrals',
                    'example':    'She found her new job through her professional network rather than a job board.',
                },
                {
                    'word':       'employment gap',
                    'definition': 'a period on a resume where a person was not employed',
                    'example':    'Employers sometimes ask candidates to explain an employment gap.',
                },
            ],
        },
    },

    # ── ★★☆ PRACTICE ────────────────────────────────────────────────────────
    {
        'freq':     'medium',
        'filename': '02_Career_Job_Interview_Preparation_Band9-10.mp4',
        'job_data': {
            'task_num':     1,
            'band':         '9_10',
            'category':     'Career & Work',
            'category_slug':'career_work',
            'freq':         'medium',
            'title':        'Job Interview Preparation',
            'question': (
                "Your friend says: \"I have a job interview next week for my dream "
                "position, but I'm terrible at interviews. I get nervous, forget what "
                "to say, and stumble over my words. The last three times I interviewed, "
                "I didn't get the job. What advice can you give me?\""
            ),
            'answer': (
                "First, let me reassure you that interview anxiety is extremely common, "
                "and the good news is that interviewing is a skill you can absolutely "
                "improve with deliberate preparation. "
                "The fact that you have been securing interviews tells me your resume "
                "and qualifications are strong — now it is about demonstrating those "
                "qualities effectively under pressure. "
                "The most impactful thing you can do this week is practise out loud. "
                "Ask a trusted friend or family member to run mock interviews with you, "
                "using common questions such as 'Tell me about yourself' and "
                "'What is your greatest weakness?' "
                "Hearing yourself speak your answers reduces the shock of doing it for "
                "the first time in a real interview setting. "
                "Second, prepare specific examples using the STAR method — "
                "Situation, Task, Action, and Result. "
                "Instead of giving vague answers, walk the interviewer through a concrete "
                "story about a real challenge you faced and how you resolved it. "
                "Structured stories are far more memorable and persuasive than "
                "general statements about your skills. "
                "On the day itself, arrive ten minutes early so you have time to compose "
                "yourself, and remember that taking a brief pause before answering "
                "a question is completely acceptable — it signals thoughtfulness, "
                "not uncertainty. "
                "Finally, research the company thoroughly so that you can ask "
                "insightful questions at the end of the interview. "
                "Candidates who show genuine interest in the organisation always "
                "leave a stronger impression."
            ),
            'vocab': [
                {
                    'word':       'deliberate preparation',
                    'definition': 'careful, intentional practice aimed at improving a specific skill',
                    'example':    'Deliberate preparation before an interview dramatically increases confidence.',
                },
                {
                    'word':       'mock interview',
                    'definition': 'a practice interview designed to simulate the real experience',
                    'example':    'She did three mock interviews with her mentor before the real one.',
                },
                {
                    'word':       'STAR method',
                    'definition': 'a framework for answering behavioural questions: Situation, Task, Action, Result',
                    'example':    'Using the STAR method helped him give clear, structured answers.',
                },
                {
                    'word':       'persuasive',
                    'definition': 'good at convincing people to believe or do something',
                    'example':    'Her persuasive answer about leadership impressed the entire panel.',
                },
                {
                    'word':       'insightful',
                    'definition': 'showing a clear and deep understanding of something',
                    'example':    'Asking insightful questions shows the interviewer you have done your research.',
                },
                {
                    'word':       'composure',
                    'definition': 'a calm, controlled state of mind, especially in a stressful situation',
                    'example':    'He maintained his composure throughout the difficult interview.',
                },
            ],
        },
    },

    # ── ★☆☆ BONUS CHALLENGE ─────────────────────────────────────────────────
    {
        'freq':     'lower',
        'filename': '03_Career_Long_Commute_Worth_It_Band9-10.mp4',
        'job_data': {
            'task_num':     1,
            'band':         '9_10',
            'category':     'Career & Work',
            'category_slug':'career_work',
            'freq':         'lower',
            'title':        'Long Commute — Is It Worth It?',
            'question': (
                "Your friend says: \"I got a great job but the commute is three hours "
                "a day by public transit. After two months I'm exhausted, I'm not "
                "sleeping enough, and I feel like I spend my whole life on the bus. "
                "Is there a way to make this work, or should I look for "
                "something closer to home?\""
            ),
            'answer': (
                "A three-hour daily commute is genuinely significant, and the fact that "
                "it is already affecting your sleep and energy levels after just two "
                "months is a clear signal that this situation is not sustainable "
                "over the long term. "
                "Before making any major decisions, however, I would encourage you to "
                "explore a few practical options first. "
                "The most immediate thing I would suggest is speaking with your manager "
                "about flexible arrangements. "
                "Many employers today are open to working from home two or three days "
                "a week, which would reduce your weekly commute time significantly — "
                "even one remote day makes a meaningful difference to your recovery "
                "and your schedule. "
                "You might also consider how you are currently using that transit time. "
                "Three hours on public transport is actually an opportunity to listen "
                "to audiobooks, professional podcasts, or even language learning programmes "
                "— transforming what feels like wasted time into something genuinely "
                "productive or restorative. "
                "If neither of those options improves the situation, then I would "
                "seriously consider whether relocating closer to your workplace is "
                "financially feasible. "
                "The cost of moving might well be offset by lower commuting expenses, "
                "and more importantly, reclaiming three hours every day would be "
                "immeasurable in terms of your health and quality of life. "
                "Ultimately, no job opportunity is worth long-term exhaustion. "
                "If flexibility and relocation are both genuinely off the table, "
                "then yes — looking for a closer opportunity is absolutely the right call."
            ),
            'vocab': [
                {
                    'word':       'sustainable',
                    'definition': 'able to be maintained over a long period without causing harm or burnout',
                    'example':    'Working 70 hours a week is not sustainable, no matter how passionate you are.',
                },
                {
                    'word':       'flexible arrangement',
                    'definition': 'a work agreement that allows adjustments to hours, location, or schedule',
                    'example':    'The company offered flexible arrangements after the pandemic.',
                },
                {
                    'word':       'restorative',
                    'definition': 'having the ability to restore health, strength, or a feeling of well-being',
                    'example':    'She found listening to music during her commute deeply restorative.',
                },
                {
                    'word':       'feasible',
                    'definition': 'possible and practical to achieve given the available resources',
                    'example':    'Relocating was not financially feasible for the family at that time.',
                },
                {
                    'word':       'offset',
                    'definition': 'to counterbalance or compensate for the effect of something negative',
                    'example':    'The savings on transport helped offset the higher cost of the new apartment.',
                },
                {
                    'word':       'reclaim',
                    'definition': 'to recover something previously lost or taken away',
                    'example':    'Working from home allowed her to reclaim two hours of her day.',
                },
            ],
        },
    },
]


# ── Runner ────────────────────────────────────────────────────────────────────

def _progress(msg, pct):
    bar = '#' * (pct // 5) + '-' * (20 - pct // 5)
    print(f'\r  [{bar}] {pct:3d}%  {msg:<40}', end='', flush=True)


def run():
    print(f'\nOutput folder: {OUTPUT_DIR}\n')
    total = len(SAMPLES)

    for idx, sample in enumerate(SAMPLES, 1):
        freq       = sample['freq']
        filename   = sample['filename']
        job_data   = sample['job_data']
        out_path   = os.path.join(OUTPUT_DIR, filename)

        print(f'[{idx}/{total}]  {filename}')

        # Reproducible seeds — different per section so decoration varies per section
        base_seed    = idx * 1000
        section_seeds = {s: base_seed + s * 137 for s in range(1, 6)}

        t0 = time.time()
        try:
            build_video(
                job_data      = job_data,
                section_seeds = section_seeds,
                voice         = 'af_heart',
                output_path   = out_path,
                progress_cb   = _progress,
            )
            elapsed = time.time() - t0
            print(f'\n  OK  Done in {elapsed:.0f}s  ->  {out_path}\n')
        except Exception as e:
            print(f'\n  FAILED: {e}\n')
            import traceback; traceback.print_exc()

    print('\nAll samples complete.\n')


if __name__ == '__main__':
    run()
