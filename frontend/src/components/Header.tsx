import {
  Alignment,
  Navbar,
  NavbarDivider,
  NavbarGroup,
  NavbarHeading,
  Tag,
} from '@blueprintjs/core'
import { useSystemStatus } from '../app/system-status'

export function Header() {
  const system = useSystemStatus()
  const cameraOnline = system.backendState === 'online' && system.cameraError === null

  return (
    <Navbar className="vision-navbar" fixedToTop>
      <NavbarGroup align={Alignment.LEFT}>
        <NavbarHeading className="vision-navbar__brand">TAPBOT</NavbarHeading>
        <NavbarDivider />
        <span className="vision-navbar__workspace">Vision Workspace</span>
      </NavbarGroup>
      <NavbarGroup align={Alignment.RIGHT} className="vision-navbar__status">
        <span>Backend</span>
        <Tag
          intent={
            system.backendState === 'online'
              ? 'success'
              : system.backendState === 'connecting'
                ? 'warning'
                : 'danger'
          }
          minimal
        >
          {system.backendState.toUpperCase()}
        </Tag>
        <span>Camera</span>
        <Tag intent={cameraOnline ? 'success' : 'danger'} minimal>
          {cameraOnline ? 'ONLINE' : 'OFFLINE'}
        </Tag>
      </NavbarGroup>
    </Navbar>
  )
}
