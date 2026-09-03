export default function SectionHeader({ title, description, action }) {
    return (
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
                <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
                    {title}
                </h2>
                {description ? (
                    <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                        {description}
                    </p>
                ) : null}
            </div>
            {action ? <div>{action}</div> : null}
        </div>
    )
}
