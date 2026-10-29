public class newV {
    // bonus tested on the hours: 10 * hours + 5 > 405 exactly when hours > 40
    public static double snippet(int hours) {
        int base = 0;
        int pay = 0;
        int bonus = 0;
        base = hours * 10;
        pay = base + 5;
        if (hours > 40) {
            bonus = 1;
        }
        return bonus;
    }
}
