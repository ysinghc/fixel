import { paths } from '../paths'
import { ButtonLink, Empty } from '../components/ui'

export function NotFound() {
  return (
    <div className="mx-auto max-w-3xl p-4 md:p-8">
      <Empty title="There is no page here" action={<ButtonLink to={paths.home} kind="primary">Go home</ButtonLink>}>The link may be from an older version of Fixel.</Empty>
    </div>
  )
}
