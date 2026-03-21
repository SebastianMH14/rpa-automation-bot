import logging
import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains

logger = logging.getLogger("bot")


def marcar_radio(driver, input_radio, ins_element, timeout: int = 10) -> bool:
    """
    Marca un radio button estilizado con iCheck mediante tres estrategias
    progresivas (clic directo, JS con eventos iCheck, ActionChains).

    Args:
        driver      : instancia de Selenium WebDriver.
        input_radio : el elemento <input type='radio'>.
        ins_element : el <ins> decorativo asociado al input (el que iCheck renderiza).
        timeout     : segundos máximos de espera para validar el estado checked.

    Returns:
        True si el radio quedó marcado, False si ninguna estrategia funcionó.
    """
    driver.execute_script("arguments[0].scrollIntoView(true);", ins_element)
    time.sleep(0.3)

    # Estrategia 1: clic directo sobre el ins
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: ins_element.is_displayed() and ins_element.is_enabled()
        )
        ins_element.click()
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return arguments[0].checked;", input_radio)
        )
        logger.info("✅ Consentimiento marcado (estrategia 1 - clic directo)")
        return True
    except Exception:
        pass

    # Estrategia 2: forzar checked + disparar eventos iCheck
    driver.execute_script(
        """
        var input = arguments[0];
        input.checked = true;
        input.dispatchEvent(new Event('ifChecked', { bubbles: true }));
        input.dispatchEvent(new Event('change',    { bubbles: true }));
        input.dispatchEvent(new Event('click',     { bubbles: true }));
        """,
        input_radio,
    )
    if driver.execute_script("return arguments[0].checked;", input_radio):
        logger.info("✅ Consentimiento marcado (estrategia 2 - JS + eventos iCheck)")
        return True

    # Estrategia 3: ActionChains
    ActionChains(driver).move_to_element(ins_element).click().perform()
    time.sleep(0.3)
    if driver.execute_script("return arguments[0].checked;", input_radio):
        logger.info("✅ Consentimiento marcado (estrategia 3 - ActionChains)")
        return True

    logger.error("❌ No se pudo marcar el consentimiento informado")
    return False