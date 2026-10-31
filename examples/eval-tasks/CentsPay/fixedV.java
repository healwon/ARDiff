public class fixedV {
    // reference fix: keep cents, scale the threshold correctly (405 * 100)
    public static double snippet(int hours) {
        int base = 0;
        int pay = 0;
        int bonus = 0;
        base = hours * 1000;
        pay = base + 500;
        if (pay > 40500) {
            bonus = 1;
        }
        return bonus;
    }
}
