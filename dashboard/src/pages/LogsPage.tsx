import LogViewer from '../components/logs/LogViewer'
import { PageHeader } from '../components/layout/PageHeader'
import { useTranslation } from '../i18n/useTranslation'

export default function LogsPage() {
  const { t } = useTranslation()
  return (
    <>
      <PageHeader title={t('logs.title')} description={t('logs.description')} />
      <LogViewer />
    </>
  )
}
