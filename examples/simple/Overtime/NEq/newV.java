public class newV {
    // "tidied" bound: a pay of exactly 405 (40 hours) now gets the bonus
    public static double snippet(int hours) {
        int base = 0;
        int pay = 0;
        int bonus = 0;
        base = hours * 10;
        pay = base + 5;
        if (pay >= 405) {
            bonus = 1;
        }
        return bonus;
    }
}
